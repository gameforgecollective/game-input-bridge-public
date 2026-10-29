// Optional persistent stdio client. Paths resolve from this checkout.
import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));

export async function connectGameBridge({
  python = process.env.GAME_INPUT_PYTHON || resolve(root, '.venv', 'Scripts', 'python.exe'),
  serverPath = resolve(root, 'game_input_mcp.py'),
  requestTimeoutMs = 45000,
} = {}) {
  if (!Number.isInteger(requestTimeoutMs) || requestTimeoutMs < 100 || requestTimeoutMs > 90000) {
    throw new Error('requestTimeoutMs must be an integer from 100 to 90000.');
  }
  const child = spawn(python, [serverPath], {
    cwd:dirname(serverPath), windowsHide:true, stdio:['pipe', 'pipe', 'pipe'],
  });
  const closed = new Promise(resolveClose => child.once('close', resolveClose));
  let nextId = 0, buffer = '', stderr = '', stopped = false;
  const pending = new Map();
  function failAll(error) {
    stopped = true;
    for (const request of pending.values()) {
      clearTimeout(request.timer);
      request.reject(error);
    }
    pending.clear();
  }
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-2000); });
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', chunk => {
    buffer += chunk;
    let newline;
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (!line.trim()) continue;
      let message;
      try { message = JSON.parse(line); }
      catch {
        failAll(new Error('Invalid local MCP response; observe before repeating input.'));
        child.kill();
        return;
      }
      const request = pending.get(message.id);
      if (!request) continue;
      pending.delete(message.id);
      clearTimeout(request.timer);
      if (message.error) request.reject(new Error(JSON.stringify(message.error)));
      else request.resolve(message.result);
    }
  });
  child.on('error', failAll);
  child.on('exit', (code, signal) => failAll(new Error(`Local bridge exited (${code ?? signal}). ${stderr}`)));
  function request(method, params = {}) {
    if (stopped) return Promise.reject(new Error('The bridge connection is closed.'));
    const id = ++nextId;
    return new Promise((resolveRequest, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('Bridge request timed out; observe before repeating input.'));
      }, requestTimeoutMs);
      pending.set(id, {resolve:resolveRequest, reject, timer});
      child.stdin.write(JSON.stringify({jsonrpc:'2.0', id, method, params}) + '\n', error => {
        if (error) { clearTimeout(timer); pending.delete(id); reject(error); }
      });
    });
  }
  let initialized;
  try {
    initialized = await request('initialize', {
      protocolVersion:'2025-06-18', capabilities:{},
      clientInfo:{name:'game-input-bridge-client', version:'0.1.0-preview'},
    });
    child.stdin.write(JSON.stringify({jsonrpc:'2.0', method:'notifications/initialized'}) + '\n');
  } catch (error) { child.kill(); throw error; }
  return {
    pid:child.pid,
    instructions:initialized.instructions || '',
    serverInfo:initialized.serverInfo,
    call:(name, args = {}) => request('tools/call', {name, arguments:args}),
    listTools:() => request('tools/list'),
    step:(expectedWindow, args = {}) => request('tools/call', {
      name:'play_step', arguments:{keys:[], ...args, expected_window:expectedWindow},
    }),
    sequence:(expectedWindow, steps) => request('tools/call', {
      name:'play_sequence', arguments:{expected_window:expectedWindow, steps},
    }),
    async close({releaseInputs = true} = {}) {
      try {
        if (!stopped && releaseInputs) await request('tools/call', {name:'release_all_inputs', arguments:{}});
      } finally {
        child.stdin.end();
        await closed;
      }
    },
  };
}

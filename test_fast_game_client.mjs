import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { connectGameBridge } from './fast_game_client.mjs';

test('portable client handles spaced paths and sends only requested calls', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'bridge portable '));
  const server = join(directory, 'mock server.mjs');
  await writeFile(server, `import readline from 'node:readline';
    const lines=readline.createInterface({input:process.stdin});
    lines.on('line',line=>{const q=JSON.parse(line);if(q.id===undefined)return;
      const result=q.method==='initialize'?{protocolVersion:'2025-06-18',capabilities:{},serverInfo:{name:'mock',version:'1'}}:
      q.method==='tools/list'?{tools:[{name:'sample_tool'}]}:{structuredContent:q.params};
      process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:q.id,result})+'\\n');});`);
  let client;
  try {
    client = await connectGameBridge({python:process.execPath, serverPath:server});
    assert.equal((await client.listTools()).tools[0].name, 'sample_tool');
    const response = await client.step('My Window', {keys:[], expected_window:'Wrong Window'});
    assert.equal(response.structuredContent.name, 'play_step');
    assert.equal(response.structuredContent.arguments.expected_window, 'My Window');
  } finally {
    if (client) await client.close({releaseInputs:false});
    await rm(directory, {recursive:true, force:true});
  }
});

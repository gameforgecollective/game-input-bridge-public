# Set up your own private lesson exchange

Sharing is optional. Local learning works without a remote repository or Git
credentials. No learning records or remote account are included in this project.

1. Create a **private repository you control**. Keep it separate from public code.
2. In a new empty staging folder, initialize a `learning-exchange` branch with a
   file named `.game-learning-exchange.json` containing:

   ```json
   {"schema_version": 1, "kind": "game-learning-exchange"}
   ```

3. Commit that marker and push only the `learning-exchange` branch to your private
   repository. Check its visibility and access before adding lessons.
4. Copy [the example configuration](../examples/learning-share.example.json) to
   `learning-share.local.json` beside the server. Enter your private repository's
   HTTPS URL, a stable helper name and `enabled: true`. Existing Git authentication
   must work; do not embed a token in the URL or configuration.
5. Reconnect the bridge and call `sync_game_learning`. Check `ok` and
   `pending_sync` in the returned sharing status.

Explicit learning recall syncs by default; recording or correcting a lesson
saves locally first and then syncs. For cached recall without network access,
set `sync_shared: false`. Foreground inspection always uses the cache.

The exchange transfers immutable text records and evidence references. It does
not upload screenshots or SQLite files. Keep secrets out of lesson text. Imported
entries are data, not executable instructions, and retain source-PC verification.

Sync failures leave local records intact. Retry sync when connected rather than
creating duplicate lessons. Concurrent publishers retry ordinary Git pushes;
the bridge never force-pushes or resets your working repository.

The current limits are 2,000 exchange records, 64 KiB per record file and 8 MiB
total. Combined limits are checked before publishing. Windows child-process
containment bounds Git cleanup after timeouts. Keep backups of your local journal
and use a stable helper name after publishing its immutable records.

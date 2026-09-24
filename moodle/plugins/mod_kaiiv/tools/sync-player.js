// Bring the player's licence notices into the plugin.
//
// player.min.js carries the forked H5P code, so the plugin has to carry the
// notices that code may only be handed on with — thirdparty/ in the player is
// the one copy that is edited, and this puts the same files here on every
// build. tools/package.py refuses to package the plugin without them.

const fs = require('fs');
const path = require('path');

const from = path.resolve(__dirname, '../../../../kaiiv-player/thirdparty');
const to = path.resolve(__dirname, '../thirdparty');

fs.mkdirSync(to, {recursive: true});
for (const name of fs.readdirSync(from)) {
    fs.copyFileSync(path.join(from, name), path.join(to, name));
}
process.stdout.write('copied ' + fs.readdirSync(from).length + ' notice(s) into thirdparty/\n');

// The other half of the build.
//
// Most of this plugin goes through webpack, because the forked code is ES
// modules and a copy of an ES module is a file the browser refuses to load.
// amd/src/backend.js is the exception: it is plain AMD, it has no imports, and
// a copy of it is a correct build — the same arrangement mod_kaivideo uses for
// all of its sources.
//
// It is kept out of the bundle for a reason rather than an aesthetic. It calls
// requirejs at runtime for two things that should only ever be fetched when
// they are needed — Moodle's video.js for an HLS stream, Vimeo's SDK for a
// Vimeo video — and a bundler resolves those at build time. That turns two
// conditional downloads into two unconditional ones, and fails outright on the
// Vimeo URL, which is not a file that exists at build time anywhere.
//
// Runs after webpack, because webpack cleans the output directory.

const fs = require('fs');
const path = require('path');

const PLAIN = ['backend.js'];

const src = path.resolve(__dirname, '../amd/src');
const build = path.resolve(__dirname, '../amd/build');

fs.mkdirSync(build, {recursive: true});

let failed = false;

for (const name of PLAIN) {
    const from = path.join(src, name);
    const to = path.join(build, name.replace(/\.js$/, '.min.js'));
    const source = fs.readFileSync(from, 'utf8');

    // The check that makes a copy safe. If somebody adds an import to this
    // file, copying it produces something the browser cannot load, and the
    // failure would otherwise appear as a syntax error in a learner's console
    // rather than here.
    if (/^\s*(import|export)\s/m.test(source)) {
        process.stderr.write(
            name + ' now uses ES module syntax, so copying it is no longer a '
            + 'build. Move it into the webpack entry instead.\n');
        failed = true;
        continue;
    }

    fs.writeFileSync(to, source);
    process.stdout.write('copied ' + path.relative(process.cwd(), to) + '\n');
}

process.exit(failed ? 1 : 0);

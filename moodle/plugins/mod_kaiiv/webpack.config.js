// Bundling the fork into something Moodle can load.
//
// mod_kaivideo next door has a build script that copies amd/src to amd/build,
// and for that plugin a copy is a correct build: its sources are plain AMD,
// so nothing needs transforming. This one cannot do that. The forked code is
// ES modules — `import Interaction from './interaction'` is the first line of
// interactive-video.js — and a copied file with an import statement in it
// loads as a script and fails with a syntax error at the moment a learner
// opens the activity.
//
// So there is a real bundler here. tests/check_fork.py refuses a build
// directory containing import statements, which is the specific mistake this
// file exists to prevent somebody making by hand.
//
//     npm install && npm run build
//
// The output is committed, like Moodle's own amd/build directories, because a
// customer installing this plugin has a PHP host and not a node toolchain.

const path = require('path');

module.exports = (env, argv) => ({
    entry: {
        player: './amd/src/player.js',
    },

    output: {
        path: path.resolve(__dirname, 'amd/build'),
        // Moodle loads amd/build/<name>.min.js whatever is actually in it.
        filename: '[name].min.js',
        // AMD, because that is what Moodle's loader speaks. Without this the
        // bundle would define a global and Moodle's require would resolve to
        // undefined — which fails as "init is not a function", a message that
        // says nothing about the cause.
        libraryTarget: 'amd',
        // Named, so that Moodle's requirejs — which asks for a named module —
        // finds what the bundle defines. An anonymous define() works when a
        // loader fetches the file by path and fails when it looks it up by
        // name, which is what js_call_amd does.
        library: 'mod_kaiiv/player',
        clean: true,
    },

    // Moodle ships these and loads them itself. Bundling our own copy of
    // jQuery would put a second jQuery on the page, and the one the forked
    // code got would not be the one Moodle's other modules are using.
    externals: {
        'jquery': 'jquery',
        // jQuery UI, for the seekbar. The forked code builds it with
        // $.fn.slider, which is one of its declared H5P dependencies upstream
        // (jQuery.ui 1.10 in library.json).
        //
        // 'jqueryui' is the name Moodle's own requirejs config gives it —
        // lib/requirejs/moodle-config.js, alongside 'jquery' itself — and it
        // resolves to ui-1.14.1. Worth stating because guessing it wrong is
        // not a missing feature: requirejs cannot resolve the module, the
        // whole bundle never runs, and the page shows nothing at all.
        //
        // Every module is mapped to 'jqueryprivate' for its jquery
        // dependency, and jquery-private returns $.noConflict(true) of the
        // same object — so the .slider jQuery UI installs is on the same $.fn
        // the fork holds.
        'jqueryui': 'jqueryui',
        'core/log': 'core/log',
        'core/ajax': 'core/ajax',
        'core/str': 'core/str',
        'core/notification': 'core/notification',
        // Ours, but not bundled: it makes conditional runtime require() calls
        // that a bundler would resolve eagerly. See amd/src/h5pcompat.js.
        'mod_kaiiv/backend': 'mod_kaiiv/backend',
    },

    resolve: {
        alias: {
            // The forked code imports h5p-lib-controls by its npm name. We
            // vendored it instead of depending on it, because a customer
            // install has no node_modules — see thirdparty/README.md.
            //
            // Aliased rather than rewritten in the forked files: those import
            // lines are upstream's, and every one we edit is a line that
            // conflicts the next time we take a patch.
            'h5p-lib-controls/src/scripts': path.resolve(
                __dirname, 'amd/src/libcontrols'),
        },
    },

    module: {
        rules: [
            {
                test: /\.js$/,
                // The forked code is not excluded. It is ours now, it is ES
                // modules, and it needs the same treatment as everything
                // else — excluding it as though it were a dependency is how
                // half a bundle ends up untranspiled.
                exclude: /node_modules/,
                use: {
                    loader: 'babel-loader',
                    options: {
                        presets: [['@babel/preset-env', {
                            // What Moodle itself targets. Going further back
                            // costs bundle size for browsers nobody watching
                            // a video on this stack is using; going forward
                            // breaks the customer still on an old managed
                            // desktop, which is a real customer.
                            targets: '> 0.5%, last 2 versions, not dead',
                        }]],
                    },
                },
            },
        ],
    },

    // Source maps in development only. A production map would ship 8,500
    // lines of forked source to every learner's browser on every page load.
    devtool: argv.mode === 'development' ? 'source-map' : false,

    performance: {
        // The fork is large and that is a known, accepted cost of not having
        // written it. A warning on every build trains people to ignore
        // warnings on every build.
        hints: false,
    },
});

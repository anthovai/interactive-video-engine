// Bundling the player into something Moodle can load.
//
// The player's source is kaiiv-player/ at the root of this repository — the
// same code a customer loads outside Moodle — and amd/src/player.js is the
// Moodle adapter over it. This bundles the two into amd/build/player.min.js.
//
// A copy would not do, as it does for mod_kaivideo next door: the forked code
// is ES modules, and a copied file with an import statement in it loads as a
// script and fails with a syntax error at the moment a learner opens the
// activity. tests/smoke.js refuses a build containing import statements.
//
//     npm install && npm run build
//
// The output is committed, like Moodle's own amd/build directories, because a
// customer installing this plugin has a PHP host and not a node toolchain.

const path = require('path');
const webpack = require('webpack');

const PLAYER = path.resolve(__dirname, '../../../kaiiv-player');
const playerPackage = require(path.join(PLAYER, 'package.json'));

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
        // The player imports its slider under this name so that each build
        // can supply its own: the standalone one bundles jQuery UI's slider,
        // and this one maps it to the jQuery UI Moodle already loads.
        'kaiiv-jqueryui': 'jqueryui',
    },

    resolve: {
        alias: {
            // The player, from source. One copy of it in the repository, not
            // one per system it is used in.
            'kaiiv-player': path.join(PLAYER, 'src/index.js'),
            // The forked code imports h5p-lib-controls by its npm name; it is
            // vendored in the player (see kaiiv-player/thirdparty/README.md).
            // Aliased rather than rewritten in the forked files, which are
            // kept as upstream wrote them.
            'h5p-lib-controls/src/scripts': path.join(PLAYER, 'src/libcontrols'),
        },
    },

    plugins: [
        new webpack.DefinePlugin({KAIIV_PLAYER_VERSION: JSON.stringify(playerPackage.version)}),
    ],

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

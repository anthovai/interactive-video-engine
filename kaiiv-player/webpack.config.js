// The standalone build: what a customer's page loads.
//
//     dist/kaiiv-player.js       <script src>, defines window.KaiivPlayer
//     dist/kaiiv-player.esm.js   import {create} from '@kaiser/kaiiv-player'
//     dist/kaiiv-player.css      from tools/build-styles.js
//
// jQuery and jQuery UI's slider are bundled in, at the versions Moodle 5.1
// ships (3.7.1 and 1.14.1), because that is what the fork was tested against
// and a customer's page may have no jQuery or a different one. They are the
// bundle's own copy, reached only through the import inside it; nothing is
// put on window except KaiivPlayer and the H5P runtime the fork needs.
//
// A plain global rather than UMD for the script build. UMD on a page that has
// an AMD loader — any Moodle page, many older sites — calls define()
// anonymously, and RequireJS rejects that with "Mismatched anonymous
// define()". A global works on every page; bundler users take the ESM file.
//
// mod_kaiiv has its own build over the same src/, in its webpack.config.js,
// with Moodle's jQuery in place of this one.

const path = require('path');
const webpack = require('webpack');
const pkg = require('./package.json');

const common = (argv) => ({
    entry: './src/index.js',
    resolve: {
        alias: {
            // The seekbar's slider, and only that — it is the one jQuery UI
            // widget the fork uses.
            'kaiiv-jqueryui': 'jquery-ui/ui/widgets/slider',
            // The fork imports h5p-lib-controls by its npm name; it is
            // vendored in src/libcontrols (see thirdparty/README.md).
            // Aliased rather than rewritten in the forked files, which are
            // kept as upstream wrote them.
            'h5p-lib-controls/src/scripts': path.resolve(__dirname, 'src/libcontrols'),
        },
    },
    module: {
        rules: [{
            test: /\.js$/,
            exclude: /node_modules/,
            use: {
                loader: 'babel-loader',
                options: {
                    presets: [['@babel/preset-env', {
                        targets: '> 0.5%, last 2 versions, not dead',
                    }]],
                },
            },
        }],
    },
    plugins: [
        new webpack.DefinePlugin({KAIIV_PLAYER_VERSION: JSON.stringify(pkg.version)}),
        new webpack.BannerPlugin({
            banner: `@kaiser/kaiiv-player ${pkg.version}. Includes h5p-interactive-video and `
                + 'h5p-lib-controls (MIT, H5P), jQuery and jQuery UI (MIT, OpenJS Foundation). '
                + 'See thirdparty/.',
        }),
    ],
    devtool: argv.mode === 'development' ? 'source-map' : false,
    performance: {hints: false},
});

module.exports = (env, argv) => [
    {
        ...common(argv),
        output: {
            path: path.resolve(__dirname, 'dist'),
            filename: 'kaiiv-player.js',
            library: {name: 'KaiivPlayer', type: 'window'},
        },
    },
    {
        ...common(argv),
        experiments: {outputModule: true},
        output: {
            path: path.resolve(__dirname, 'dist'),
            filename: 'kaiiv-player.esm.js',
            library: {type: 'module'},
        },
    },
];

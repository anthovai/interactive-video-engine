// KAISER interactive video player — the public entry point.
//
//     const player = await KaiivPlayer.create(element, {
//         video: {provider: 'file', src: '/lessons/intro.mp4'},
//         items,                      // from your server, which got them from
//                                     // the engine's /timeline
//         mustanswer: true,
//         answer: (id, response) =>   // your server, which asks the engine's
//             fetch(...).then(r => r.json()),   // /judge and stores the result
//         progress: ({position, finished, leaving}) => {...},   // optional
//     });
//
// The browser never marks anything and never holds an answer. `items` is what
// the engine chose to let the learner see, and `answer` goes to a server that
// asks the engine. A page that called the engine directly would hand every
// learner the key to it; see README.md.
//
// Import order in this file is load-bearing. The forked modules read a bare
// global `H5P` in their own top-level statements — `const $ = H5P.jQuery;` is
// the first line of interactive-video.js — which runs when the module is
// evaluated. So './h5pcompat' has to be imported before './player', which
// imports the fork. ES module imports are evaluated in the order written;
// moving this line down breaks the player at load.
import './h5pcompat';

// Imported for its effect on jQuery: it puts .slider on $.fn, which the fork
// builds its seekbar with. Resolved by the build — to jQuery UI's own slider
// in the standalone bundle, to the jQuery UI Moodle already loads in the
// plugin's — so that there is only ever one jQuery on the page.
import 'kaiiv-jqueryui';

import Player from './player';
import Log, {setLogger} from './log';
import {configure as configureBackend} from './backend';
import {resolveStrings, LANGUAGES} from './strings';

const PROVIDERS = ['file', 'hls', 'youtube', 'vimeo'];

/**
 * @param {String} tag
 * @param {Object} attrs
 * @param {Array} children
 * @returns {Element}
 */
const el = (tag, attrs, children) => {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([name, value]) => {
        if (value !== undefined && value !== null && value !== false) {
            node.setAttribute(name, value === true ? '' : String(value));
        }
    });
    (children || []).forEach((child) => node.appendChild(child));
    return node;
};

/**
 * The element the video plays in, for a page that did not supply one.
 *
 * A real <video> for a file and for a stream. For YouTube and Vimeo, the
 * element their SDK replaces with its iframe. Vimeo gets a transparent sheet
 * over it: its own controls can be asked to go away, but whether that is
 * honoured depends on the account the video sits in, so they are put out of
 * reach instead.
 *
 * @param {Object} video
 * @returns {Element}
 */
const buildFrame = (video) => {
    const frame = el('div', {'class': 'ratio ratio-16x9 kaiiv-ratio'});
    if (video.provider === 'youtube') {
        frame.appendChild(el('div', {'data-region': 'youtube'}));
    } else if (video.provider === 'vimeo') {
        frame.appendChild(el('div', {'data-region': 'vimeo'}));
        frame.appendChild(el('div', {'class': 'kaiiv-shield', 'data-region': 'shield'}));
    } else {
        frame.appendChild(el('video', {
            'data-region': 'video',
            'preload': 'metadata',
            'playsinline': true,
            // A stream is attached by the backend, not declared: a .m3u8 on a
            // <video> that cannot decode it reports "no supported sources"
            // before anything has had a chance to attach.
            'src': video.provider === 'file' ? video.src : null,
            'crossorigin': video.crossorigin || null,
        }));
    }
    return frame;
};

/**
 * Find or make the .kaiiv root and its stage inside the given element.
 *
 * A page may render the markup itself — mod_kaiiv does, so that the video is
 * on the page before any script runs — or hand over an empty element and let
 * this build it.
 *
 * @param {Element} container
 * @param {Object} video
 * @returns {Element} the root
 */
const prepare = (container, video) => {
    let root = container.matches('[data-region="kaiiv"]')
        ? container : container.querySelector('[data-region="kaiiv"]');
    if (!root) {
        root = el('div', {'class': 'kaiiv kaiiv-standalone', 'data-region': 'kaiiv'});
        container.appendChild(root);
    }
    root.setAttribute('data-state', 'loading');
    root.setAttribute('data-provider', video.provider);

    let stage = root.querySelector('[data-region="stage"]');
    if (!stage) {
        stage = el('div', {'class': 'kaiiv-stage', 'data-region': 'stage'});
        root.appendChild(stage);
    }
    if (!stage.querySelector('[data-region="video"], [data-region="youtube"], [data-region="vimeo"]')) {
        stage.appendChild(buildFrame(video));
    }
    return root;
};

/**
 * @param {Object} given
 * @returns {Object} the video, normalised
 */
const normaliseVideo = (given) => {
    const video = {...(given || {})};
    video.provider = video.provider || 'file';
    if (PROVIDERS.indexOf(video.provider) === -1) {
        throw new Error('kaiiv: video.provider must be one of ' + PROVIDERS.join(', '));
    }
    if ((video.provider === 'file' || video.provider === 'hls') && !video.src
            && !video.streamurl) {
        throw new Error('kaiiv: video.src is required for a ' + video.provider + ' video');
    }
    if ((video.provider === 'youtube' || video.provider === 'vimeo') && !video.videoid) {
        throw new Error('kaiiv: video.videoid is required for a ' + video.provider + ' video');
    }
    // The backend's own names for these.
    video.streamurl = video.provider === 'hls' ? (video.streamurl || video.src) : '';
    return video;
};

/**
 * Put a player on the page.
 *
 * @param {Element|String} target an element, or a selector for one
 * @param {Object} options
 * @param {Object} options.video {provider: file|hls|youtube|vimeo, src, videoid}
 * @param {Array} options.items what the engine's /timeline returned
 * @param {Function} options.answer (interactionId, response) => Promise<verdict>
 * @param {Function} [options.progress] ({position, finished, leaving}) => void
 * @param {Array} [options.bookmarks] [{at, label}]
 * @param {Boolean} [options.mustanswer=true] hold the video at unanswered questions
 * @param {Boolean} [options.posterstart=true] show the title on the start screen
 * @param {String} [options.title]
 * @param {Number} [options.resumeat=0] seconds; never past an unanswered question
 * @param {String} [options.lang='en'] 'en' or 'th'
 * @param {Object} [options.strings] overrides for any sentence
 * @param {Object} [options.logger] {debug, info, warn, error}
 * @param {Function} [options.attachStream] (videoElement, url) => Promise, for HLS
 * @param {Function} [options.onBackend] (backend) => void, once the video exists
 * @param {Function} [options.onAnswer] (interactionId, verdict) => void
 * @param {Function} [options.onEnd] () => void
 * @returns {Promise<Object>} {root, instance, player}
 */
export const create = (target, options) => {
    return new Promise((resolve) => {
        const container = typeof target === 'string' ? document.querySelector(target) : target;
        if (!container) {
            throw new Error('kaiiv: no element to put the player in');
        }
        const config = {...(options || {})};
        if (typeof config.answer !== 'function') {
            // Required rather than defaulted. A player with nowhere to send an
            // answer would draw every question and mark none of them, and a
            // learner would sit through the whole video believing they were
            // being assessed.
            throw new Error('kaiiv: options.answer is required');
        }
        config.video = normaliseVideo(config.video);
        config.items = Array.isArray(config.items) ? config.items : [];
        config.mustanswer = config.mustanswer !== false;
        config.posterstart = config.posterstart !== false;

        if (config.logger) {
            setLogger(config.logger);
        }
        configureBackend({attachStream: config.attachStream, onBackend: config.onBackend});

        const strings = resolveStrings(config.lang || 'en', config.strings);
        const root = prepare(container, config.video);
        const player = new Player(root, config, strings);
        player.start();
        resolve({root: root, instance: player.instance, player: player});
    }).catch((error) => {
        Log.error('kaiiv: could not start the player', error);
        throw error;
    });
};

export const languages = Object.keys(LANGUAGES);
// Filled in by the build; 'dev' when the source is imported directly.
/* global KAIIV_PLAYER_VERSION */
export const version = typeof KAIIV_PLAYER_VERSION !== 'undefined' ? KAIIV_PLAYER_VERSION : 'dev';

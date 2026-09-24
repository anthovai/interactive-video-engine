// The Moodle adapter for the KAISER interactive video player.
//
// The player itself — the forked H5P shell, the question cards, the due rule —
// is kaiiv-player/ at the root of this repository, and is the same code a
// customer loads on a page that is not Moodle. This file is what makes it a
// Moodle activity: answers go to the mod_kaiiv_answer web service, progress to
// mod_kaiiv_record_progress, the words come from this plugin's language pack,
// and a stream is attached with the video.js Moodle already ships.
//
// Bundled from source by webpack.config.js, with Moodle's own jQuery and
// jQuery UI in place of the ones the standalone build carries.

import {create} from 'kaiiv-player';

import Ajax from 'core/ajax';
import Log from 'core/log';

// A named import, and the difference is not stylistic.
//
// Moodle's AMD modules come in two shapes. core/ajax and core/log are hand
// written AMD that return an object, so a default import picks up that
// object. core/str is an ES module Moodle transpiles, so its built form sets
// __esModule and exports names only — there is no default, and importing one
// gives undefined, which fails as "cannot read properties of undefined
// (reading 'getStrings')" on the first call.
//
// To check which shape a Moodle module has, look for __esModule in its built
// file: lib/amd/build/<name>.min.js.
import {getStrings} from 'core/str';

/**
 * Moodle's string keys, and the player's name for each.
 *
 * The player's keys differ where Moodle's are unusable as property names:
 * `continue` is a reserved word, and `error:notsaved` has a colon in it.
 */
const STRINGS = {
    correct: 'correct',
    wrong: 'wrong',
    tryagain: 'tryagain',
    continuelabel: 'continue',
    submitanswer: 'submitanswer',
    youranswer: 'youranswer',
    istrue: 'istrue',
    isfalse: 'isfalse',
    pickatleastone: 'pickatleastone',
    unsupported: 'unsupportedtype',
    interactionword: 'interactionword',
    notsaved: 'error:notsaved',
    noattemptsleft: 'noattemptsleft',
    alreadycorrect: 'alreadycorrect',
    play: 'play',
    pause: 'pause',
    back10: 'back10',
};

/**
 * A web service call that outlives the page.
 *
 * An ordinary request issued from pagehide is cancelled with the document;
 * sendBeacon hands it to the browser to deliver afterwards, with no response
 * to read.
 *
 * @param {String} methodname
 * @param {Object} args
 * @returns {Boolean} whether the browser accepted it for delivery
 */
const beacon = (methodname, args) => {
    if (!navigator.sendBeacon || !window.M || !window.M.cfg) {
        return false;
    }
    const url = window.M.cfg.wwwroot + '/lib/ajax/service.php?sesskey='
        + encodeURIComponent(window.M.cfg.sesskey)
        + '&info=' + encodeURIComponent(methodname);
    const body = JSON.stringify([{index: 0, methodname: methodname, args: args}]);
    try {
        return navigator.sendBeacon(url, new Blob([body], {type: 'application/json'}));
    } catch (error) {
        return false;
    }
};

/**
 * Put an HLS stream on a <video> with Moodle's own video.js.
 *
 * Through window.require, Moodle's RequireJS, and not a bare require(): this
 * file is bundled, and webpack would take a bare one as its own and try to
 * resolve media_videojs at build time.
 *
 * @param {HTMLVideoElement} element
 * @param {String} url
 * @returns {Promise}
 */
const attachStream = (element, url) => new Promise((resolve, reject) => {
    window.require(['media_videojs/video-lazy'], (videojs) => {
        // controls false, and the element left in place: video.js keeps the
        // <video> it was given as its playback element, so the player's file
        // backend keeps driving the same element.
        const player = videojs(element, {controls: false, fluid: false});
        player.src({src: url, type: 'application/x-mpegURL'});
        resolve(element);
    }, () => reject(new Error('videojs_unavailable')));
});

export const init = (config) => {
    const root = document.querySelector('[data-region="kaiiv"]');
    if (!root || !root.querySelector('[data-region="stage"]')) {
        // The engine was unreachable and view.php rendered the failure
        // instead of the video. Nothing to do, and nothing to report: the
        // page already says what happened.
        return;
    }

    const keys = Object.keys(STRINGS);
    getStrings(keys.map((key) => ({key: STRINGS[key], component: 'mod_kaiiv'})))
        .then((resolved) => {
            const strings = {};
            keys.forEach((key, index) => {
                strings[key] = resolved[index];
            });

            return create(root, {
                video: {
                    provider: config.provider,
                    src: config.src,
                    videoid: config.videoid,
                    streamurl: config.streamurl,
                },
                items: config.items,
                bookmarks: config.bookmarks,
                mustanswer: config.mustanswer,
                posterstart: config.posterstart,
                title: config.title,
                resumeat: config.resumeat,
                strings: strings,
                logger: Log,
                attachStream: attachStream,
                // The proctoring monitor looks for this. Publishing it here
                // means a YouTube or Vimeo lesson is watchable without the
                // monitor knowing what either provider is.
                onBackend: (backend) => {
                    window.KAIVIDEO = backend;
                },

                answer: (interactionid, response) => Ajax.call([{
                    methodname: 'mod_kaiiv_answer',
                    args: {
                        cmid: config.cmid,
                        interactionid: interactionid,
                        response: JSON.stringify(response),
                    },
                }])[0],

                progress: ({position, finished, leaving}) => {
                    const args = {cmid: config.cmid, position: position, finished: finished};
                    if (leaving && beacon('mod_kaiiv_record_progress', args)) {
                        return null;
                    }
                    return Ajax.call([{
                        methodname: 'mod_kaiiv_record_progress',
                        args: args,
                    }])[0];
                },
            });
        })
        .catch((error) => {
            Log.error('kaiiv: could not start the player', error);
        });
};

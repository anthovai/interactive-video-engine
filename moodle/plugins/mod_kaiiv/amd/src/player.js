// Booting the forked player.
//
// Import order in this file is load-bearing, and it is the first thing to
// check if the page fails with "cannot read property jQuery of undefined".
//
// The forked modules read a bare global `H5P` in their own top-level
// statements — `const $ = H5P.jQuery;` is the first line of
// interactive-video.js — which runs when the module is evaluated, not when
// anything is called. So './h5pcompat' has to be imported before any of
// './iv/*', because that is what puts H5P on window.
//
// ES module imports are evaluated in the order they are written, so the order
// below is the guarantee. Moving the h5pcompat line down, or letting a tool
// sort these alphabetically, breaks the player at load with a message that
// points at the fork rather than at the reordering.
import './h5pcompat';

// Imported for its effect on jQuery, not for anything it returns: it puts
// .slider on $.fn, which is what the forked code builds its seekbar with.
// Left out, the seekbar throws when the video loads — caught by the shim's
// dispatcher, so the player still runs and the bar simply does not respond,
// which is the kind of half-working nobody files a bug about.
import 'jqueryui';

import InteractiveVideo from './iv/interactive-video';
import Interaction from './iv/interaction';
import {register as registerInteractions} from './interactions';

import $ from 'jquery';
import Ajax from 'core/ajax';
import Log from 'core/log';

// A named import, and the difference is not stylistic.
//
// Moodle's AMD modules come in two shapes. core/ajax and core/log are hand
// written AMD that return an object, so a default import picks up that
// object. core/str is an ES module Moodle transpiles, so its built form sets
// __esModule and exports names only — there is no default, and importing one
// gives undefined.
//
// It fails in the worst place: the bundle loads, the fork evaluates, and the
// page dies on the first call with "cannot read properties of undefined
// (reading 'getStrings')" — pointing at this file rather than at the import.
// jsdom did not catch it either, because a stub is whatever shape the stub
// was written in.
//
// To check which shape a Moodle module has, look for __esModule in its built
// file: lib/amd/build/<name>.min.js.
import {getStrings} from 'core/str';

const H5P = window.H5P;

// The two names the fork registers itself under and then reads back. Upstream
// this happens in its own entry point; here it happens once, here, and
// tests/check_fork.py fails the build if it stops happening.
H5P.InteractiveVideo = InteractiveVideo;
H5P.InteractiveVideoInteraction = Interaction;

/**
 * A web service call that outlives the page.
 *
 * An ordinary request issued from pagehide is cancelled with the document;
 * sendBeacon hands it to the browser to deliver afterwards, with no response
 * to read. local_kaiproctor has the same thing, and this used to import it —
 * which made this plugin impossible to install on a Moodle that did not also
 * carry the whole proctoring stack. The ten lines are repeated instead.
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

/** How often the playhead position is sent while playing. */
const REPORT_EVERY_MS = 15000;

/** The fork's notional video size in em: this.width (640) over this.fontSize
 *  (16) across, and that divided by 16:9 down. See asInteraction(). Read off
 *  iv/interactive-video.js rather than chosen; if upstream changes those two
 *  numbers, these have to follow. */
const FORK_WIDTH_EM = 640 / 16;
const FORK_HEIGHT_EM = FORK_WIDTH_EM * 9 / 16;

/** Strings the interactions need. Fetched once, before anything is drawn. */
const STRING_KEYS = [
    'correct', 'wrong', 'tryagain', 'continue', 'submitanswer', 'youranswer',
    'istrue', 'isfalse', 'pickatleastone', 'unsupportedtype', 'interactionword',
    'error:notsaved', 'play', 'pause', 'back10',
];

/**
 * One activity on one page.
 */
class Player {

    /**
     * @param {Object} config from view.php
     * @param {Object} strings resolved
     */
    constructor(config, strings) {
        this.config = config;
        this.strings = strings;
        this.root = document.querySelector('[data-region="kaiiv"]');
        this.stage = this.root && this.root.querySelector('[data-region="stage"]');
        this.lastReported = 0;
        this.finished = false;
    }

    /**
     * Build the player and put it on the page.
     */
    start() {
        if (!this.stage) {
            // The engine was unreachable and view.php rendered the failure
            // instead of the video. Nothing to do, and nothing to report:
            // the page already says what happened.
            return;
        }

        registerInteractions(H5P, {
            strings: this.strings,
            submit: (interactionid, response) => this.submit(interactionid, response),
            // Played through the video rather than the InteractiveVideo, so
            // the due rule in enforceDue() still sees it: resuming is only a
            // request, and an interaction that is still unanswered pulls the
            // playhead straight back.
            resume: () => {
                if (!this.instance) {
                    return;
                }
                // A marker interaction is shown in the dialog. Closing it
                // first is what the fork listens for to put its own state
                // back — playing underneath an open dialog leaves the video
                // running behind a panel the learner has to find the X on.
                const dialog = this.instance.dnb && this.instance.dnb.dialog;
                if (dialog && dialog.$dialog && !dialog.$dialog.prop('hidden')) {
                    dialog.close();
                }
                if (this.instance.video) {
                    this.instance.video.play();
                }
            },
        });

        // Taken out of the document before the fork touches the stage.
        //
        // attach() empties the stage and builds its own DOM in it, which
        // destroys the <video> the template put there — and the backend then
        // has nothing to drive, which surfaces as "cannot read properties of
        // null (reading 'addEventListener')" from inside backend.js.
        //
        // It is not recreated afterwards, it is put back: the proctoring
        // adapter looks for a real <video> on the page, and a fresh element
        // would leave anything already holding a reference watching a node
        // that is no longer attached to anything.
        this.reserveVideoElement();

        this.instance = new H5P.InteractiveVideo(this.params(), this.config.cmid, {});

        this.instance.attach($(this.stage));
        this.root.setAttribute('data-state', 'ready');

        this.watchPlayhead();
        this.resume();
    }

    /**
     * Hand the page's player element to the shim for safekeeping.
     *
     * One element per provider, and only one of them is ever in the markup —
     * templates/player.mustache renders the branch for the source this
     * activity has.
     */
    reserveVideoElement() {
        const element = this.stage.querySelector(
            '[data-region="video"], [data-region="youtube"], [data-region="vimeo"]');
        if (!element) {
            return;
        }

        // The framing div goes with it. A <video> with no intrinsic size and
        // nothing around it renders as a black rectangle the height of the
        // screen until metadata arrives.
        const frame = element.closest('.ratio') || element;
        frame.remove();
        H5P.reservePlayerElement(frame);
    }

    /**
     * Our config, in the shape the fork expects.
     *
     * The fork reads params.interactiveVideo, which is H5P's content format.
     * Rather than change 4,200 lines to read ours, the mapping happens here —
     * which also keeps the diff against upstream readable, and is the whole
     * reason this function is longer than it looks like it should be.
     *
     * @returns {Object}
     */
    params() {
        return {
            interactiveVideo: {
                video: {
                    // Handed straight to the shim's H5P.Video, which hands it
                    // to our own backend. The fork never looks inside it.
                    files: [this.config],
                    startScreenOptions: {
                        title: this.config.title,
                        hideStartTitle: !this.config.posterstart,
                    },
                },
                assets: {
                    interactions: (this.config.items || []).map(
                        (item) => this.asInteraction(item)),
                    bookmarks: (this.config.bookmarks || []).map((mark) => ({
                        time: mark.at,
                        label: mark.label,
                    })),
                    endscreens: [],
                },
                summary: {},
            },
            override: {
                // Upstream's own skip prevention, switched on to match our
                // setting. It is a convenience, not the rule: the rule is on
                // the server, where a learner cannot reach it. Setting it here
                // means the seekbar behaves the way the activity does rather
                // than letting a learner drag to a point the server will
                // immediately drag them back from.
                preventSkippingMode: this.config.mustanswer ? 'both' : 'none',
                showRewind10: true,
                showBookmarksmenuOnLoad: false,
            },
            l10n: {
                play: this.strings.play,
                pause: this.strings.pause,
                // The word a screen reader reads before a marker's own label.
                // It was the continue button's text once, which announced
                // every marker on the seek bar as "Continue".
                interaction: this.strings.interactionword,
            },
        };
    }

    /**
     * One of our items, as one of the fork's interactions.
     *
     * @param {Object} item
     * @returns {Object}
     */
    asInteraction(item) {
        return {
            duration: {
                from: item.start,
                // A question that pauses ends when it is answered, not when a
                // clock runs out, so its window is a moment rather than a
                // span. Given a hair of width because the fork treats
                // from === to as an interaction that is never on screen.
                // The fallback is for rows saved before timeline::window_end()
                // existed, whose end equals their start and which would
                // otherwise never be on screen. Same five seconds as the PHP.
                to: item.pauses ? item.start + 0.01
                    : (item.end > item.start ? item.end : item.start + 5),
            },
            // Position is a percentage both sides, so x and y pass through.
            // Size is not: upstream measures width and height in em against a
            // notional video 40em across (its fixed width of 640 over a font
            // size of 16) and 22.5em down at 16:9. We store percentages, which
            // is what an author means by "60% of the video".
            //
            // Passed through unconverted, 60 became 60em on a 40em video —
            // 150% — and every question was drawn over the whole frame with a
            // white background, which looked exactly like the video had
            // failed to load.
            x: item.x,
            y: item.y,
            width: item.width * FORK_WIDTH_EM / 100,
            height: item.height * FORK_HEIGHT_EM / 100,
            pause: item.pauses,
            displayType: item.display,
            label: item.label,
            // What the forked player puts in the marker's accessible name,
            // after the label. Left out it reads "Interaction. undefined" to
            // a screen reader, which sounds like a fault rather than a gap.
            libraryTitle: item.typelabel || '',
            // Marked questions are posters whatever the row says. A question
            // the learner can decline to open is not a question the video can
            // refuse to continue past, and displayType is an authoring
            // convenience rather than a licence to skip an assessment.
            ...(item.graded && item.pauses ? {displayType: 'poster'} : {}),
            action: {
                library: 'H5P.KaiivInteraction 1.0',
                params: {item: item},
            },
        };
    }

    /**
     * Send one answer to be marked.
     *
     * @param {Number} interactionid
     * @param {*} response
     * @returns {Promise} the verdict
     */
    submit(interactionid, response) {
        return Ajax.call([{
            methodname: 'mod_kaiiv_answer',
            args: {
                cmid: this.config.cmid,
                interactionid: interactionid,
                response: JSON.stringify(response),
            },
        }])[0].then((reply) => ({
            ok: reply.ok,
            error: reply.error,
            correct: reply.correct,
            revealed: reply.revealed,
            mayretry: reply.mayretry,
            attempts: reply.attempts,
            // Decoded here rather than in each renderer. The shape varies by
            // type and none of the renderers should be parsing transport.
            answers: reply.answers ? JSON.parse(reply.answers) : [],
            feedback: reply.feedback,
        })).catch((error) => {
            Log.error('kaiiv: answer call failed', error);
            return {ok: false, error: 'unreachable', correct: false,
                revealed: false, mayretry: true, attempts: 0,
                answers: [], feedback: ''};
        });
    }

    /**
     * Report where the playhead is, periodically and on the way out.
     */
    watchPlayhead() {
        // Listened to on the video, not on the player.
        //
        // The shim triggers these on the H5P.Video instance, which is where
        // upstream triggers them too. Registering them on the InteractiveVideo
        // — the obvious-looking object, since that is what we constructed —
        // silently never fires: upstream relies on H5P core bubbling events
        // from a child to its parent, and the shim does not bubble.
        //
        // Nothing complains. Progress is never reported, the due rule is never
        // enforced, and the page looks exactly as it should until somebody
        // measures it. The browser check is what found it.
        const video = this.instance.video;
        if (!video) {
            Log.error('kaiiv: the player has no video to watch');
            return;
        }

        video.on('stateUpdate', () => {
            this.enforceDue();

            if (Date.now() - this.lastReported >= REPORT_EVERY_MS) {
                this.report(false, false);
            }
        });

        video.on('stateChange', (event) => {
            if (event.data === H5P.Video.ENDED) {
                this.finished = true;
                this.report(true, false);
            }
        });

        // Both events, because neither fires reliably alone: pagehide is
        // skipped when a mobile browser is backgrounded and killed, and
        // visibilitychange does not fire on some desktop navigations.
        //
        // Sending twice is harmless — the server keeps the furthest point
        // reached, not the last one reported — and that is the only reason
        // neither of these has to know about the other.
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                this.report(this.finished, true);
            }
        });
        window.addEventListener('pagehide', () => {
            this.report(this.finished, true);
        });
    }

    /**
     * Put the playhead back if it has got past something unanswered.
     *
     * The fork has its own skip prevention, and params() switches it on. It
     * guards the seek bar, which is what a learner uses — and only that. The
     * browser check found the hole by setting video.currentTime directly:
     * the question disappeared and playback carried on, because nothing in
     * the fork is watching the element it does not own.
     *
     * Anybody with a console can do the same, and the activity claims the
     * video will not continue past an unanswered question. So the rule is
     * enforced here too, against the playhead rather than against the
     * control: at or past the point and unanswered means go back to it.
     *
     * The server is still the record — an answer skipped this way is simply
     * never marked, and the grade counts what was marked. This is what stops
     * a learner reaching the end believing they finished.
     */
    enforceDue() {
        if (!this.config.mustanswer || !this.instance || !this.instance.video) {
            return;
        }

        const at = this.instance.video.getCurrentTime();

        // `answered` is set on these same objects by interactions.js when the
        // server accepts an answer, so this reads the current state rather
        // than the state the page loaded with.
        const due = (this.config.items || []).filter(
            (item) => item.pauses && !item.answered && item.start <= at);

        if (!due.length) {
            return;
        }

        // Earliest first: sending them back to the last one they passed would
        // let them skip the ones before it.
        const first = due.reduce((a, b) => (a.start <= b.start ? a : b));

        // A margin, because the playhead is sampled rather than continuous
        // and will legitimately sit a fraction past the point the fork
        // paused at. Without it this fights the fork over tenths of a second.
        if (at > first.start + 0.5) {
            this.instance.video.pause();
            // Through the fork's own seek, not the video's. The fork keeps a
            // pointer to the next interaction it expects to show, and resets
            // it only when it is the one seeking. Seeking the video directly
            // moved the playhead back without telling it, so it went on
            // looking for whatever came after the point the learner had
            // jumped to — and showed the question at 00:08 over a playhead at
            // 00:03. Forced, because the fork's own skip rule would otherwise
            // be consulted about a seek whose whole purpose is that rule.
            this.instance.seek(first.start, {force: true});

            // And told to draw what is there. The fork renders interactions
            // from its own playback loop, which does not run while the video
            // is paused — and it is always paused here. Without this the
            // playhead came back to the question and the question did not
            // come back with it: a paused video, no card, and a learner who
            // could neither answer nor go on, for good.
            this.instance.toggleInteractions(first.start);
        }
    }

    /**
     * @param {Boolean} finished
     * @param {Boolean} leaving whether the page is going away, in which case
     *        an ordinary request would be cancelled before it left
     */
    report(finished, leaving) {
        const args = {
            cmid: this.config.cmid,
            position: this.instance.video
                ? this.instance.video.getCurrentTime() : 0,
            finished: !!finished,
        };
        this.lastReported = Date.now();

        if (leaving && beacon('mod_kaiiv_record_progress', args)) {
            return;
        }

        Ajax.call([{
            methodname: 'mod_kaiiv_record_progress',
            args: args,
        }])[0].catch(() => {
            // Progress is advisory — the grade comes from the answers — so a
            // failure here must not interrupt the lesson.
            return null;
        });
    }

    /**
     * Put the playhead back where the learner left it.
     */
    resume() {
        // Not past anything they have not answered. The server keeps the
        // furthest point reached, which can be beyond a question — they may
        // have been pulled back to it and left — and resuming there only to
        // have enforceDue() pull them straight back is two seeks where one
        // would do. Stopping just short means the question arrives by
        // playing into it, the way it did the first time.
        let target = this.config.resumeat;
        const unanswered = (this.config.items || [])
            .filter((item) => item.pauses && !item.answered && item.start < target)
            .map((item) => item.start);
        if (unanswered.length) {
            target = Math.max(0, Math.min(...unanswered) - 1);
        }

        // Below this, resuming is worse than not: it skips an opening the
        // learner has barely seen, in exchange for saving them a few seconds.
        if (target <= 5 || !this.instance.video) {
            return;
        }

        // On the video, for the reason watchPlayhead() records.
        // Through the fork's seek for the reason enforceDue() gives, and
        // forced: the fork's skip rule measures against the furthest point
        // reached in this page load, which on arrival is zero, and would
        // otherwise refuse to take the learner back to where the server
        // recorded they had got to. enforceDue() still pulls them back to
        // anything before that point they have not answered.
        this.instance.video.on('ready', () => {
            this.instance.seek(target, {force: true});
        });
    }
}

export const init = (config) => {
    getStrings(STRING_KEYS.map((key) => ({
        key: key, component: 'mod_kaiiv',
    }))).then((resolved) => {
        const strings = {};
        STRING_KEYS.forEach((key, index) => {
            // The colon in error:notsaved is not usable as a property name in
            // the renderers, so the prefix is dropped here rather than in ten
            // call sites.
            strings[key.replace('error:', '')] = resolved[index];
        });

        // Renamed rather than aliased to another string. `continue` is a
        // reserved word and reads badly as a property; `unsupportedtype` is
        // shortened only for the call sites.
        strings.continuelabel = strings.continue;
        strings.unsupported = strings.unsupportedtype;

        new Player(config, strings).start();
        return null;
    }).catch((error) => {
        Log.error('kaiiv: could not start the player', error);
    });
};

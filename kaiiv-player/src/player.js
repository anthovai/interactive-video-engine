// One lesson on one page, with whatever system it belongs to behind an adapter.
//
// Moved out of mod_kaiiv so the same player can sit in any system. What the
// Moodle version asked of Moodle — mark this answer, record how far they got —
// it now asks of the adapter the page hands in, and nothing below knows which
// system that is. See index.js for the shape of the adapter and README.md for
// what the server behind it must do.

import InteractiveVideo from './iv/interactive-video';
import Interaction from './iv/interaction';
import {register as registerInteractions} from './interactions';
import Log from './log';

import $ from 'jquery';

const H5P = window.H5P;

// The two names the fork registers itself under and then reads back. Upstream
// this happens in its own entry point; here it happens once, here, and
// tests/check_fork.py fails the build if it stops happening.
H5P.InteractiveVideo = InteractiveVideo;
H5P.InteractiveVideoInteraction = Interaction;

/** How often the playhead position is sent while playing. */
const REPORT_EVERY_MS = 15000;

/** The fork's notional video size in em: this.width (640) over this.fontSize
 *  (16) across, and that divided by 16:9 down. See asInteraction(). Read off
 *  iv/interactive-video.js rather than chosen; if upstream changes those two
 *  numbers, these have to follow. */
const FORK_WIDTH_EM = 640 / 16;
const FORK_HEIGHT_EM = FORK_WIDTH_EM * 9 / 16;

/** Counter for the id the fork is given; it only has to be unique per page. */
let instances = 0;

/**
 * What an answer comes back as when the adapter could not deliver it.
 *
 * @returns {Object}
 */
const undelivered = () => ({
    ok: false, error: 'unreachable', correct: false, revealed: false,
    mayretry: true, attempts: 0, answers: [], feedback: '',
});

export default class Player {

    /**
     * @param {Element} root the .kaiiv element
     * @param {Object} config see index.js
     * @param {Object} strings resolved
     */
    constructor(root, config, strings) {
        this.root = root;
        this.stage = root.querySelector('[data-region="stage"]');
        this.config = config;
        this.strings = strings;
        this.items = config.items || [];
        this.lastReported = 0;
        this.finished = false;
        this.id = ++instances;
    }

    /**
     * Build the player and put it on the page.
     */
    start() {
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
        // destroys the <video> that was there — and the backend then has
        // nothing to drive, which surfaces as "cannot read properties of null
        // (reading 'addEventListener')" from inside backend.js.
        //
        // It is not recreated afterwards, it is put back: a proctoring
        // monitor looks for a real <video> on the page, and a fresh element
        // would leave anything already holding a reference watching a node
        // that is no longer attached to anything.
        this.reserveVideoElement();

        this.instance = new H5P.InteractiveVideo(this.params(), this.id, {});

        this.instance.attach($(this.stage));
        this.root.setAttribute('data-state', 'ready');

        this.watchPlayhead();
        this.resume();
    }

    /**
     * Hand the player element to the shim for safekeeping.
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
     * which also keeps the diff against upstream readable.
     *
     * @returns {Object}
     */
    params() {
        return {
            interactiveVideo: {
                video: {
                    // Handed straight to the shim's H5P.Video, which hands it
                    // to our own backend. The fork never looks inside it.
                    files: [this.config.video],
                    startScreenOptions: {
                        title: this.config.title || '',
                        hideStartTitle: !this.config.posterstart,
                    },
                },
                assets: {
                    interactions: this.items.map((item) => this.asInteraction(item)),
                    bookmarks: (this.config.bookmarks || []).map((mark) => ({
                        time: mark.at,
                        label: mark.label,
                    })),
                    endscreens: [],
                },
                summary: {},
            },
            override: {
                // Upstream's own skip prevention, switched on to match the
                // setting. It is a convenience, not the rule: the rule is on
                // the server, where a learner cannot reach it.
                preventSkippingMode: this.config.mustanswer ? 'both' : 'none',
                showRewind10: true,
                showBookmarksmenuOnLoad: false,
            },
            l10n: {
                play: this.strings.play,
                pause: this.strings.pause,
                // The word a screen reader reads before a marker's own label.
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
                to: item.pauses ? item.start + 0.01
                    : (item.end > item.start ? item.end : item.start + 5),
            },
            // Position is a percentage both sides, so x and y pass through.
            // Size is not: upstream measures width and height in em against a
            // notional video 40em across and 22.5em down. We store
            // percentages, which is what an author means by "60% of the
            // video"; passed through unconverted, 60 became 150% of it.
            x: item.x,
            y: item.y,
            width: item.width * FORK_WIDTH_EM / 100,
            height: item.height * FORK_HEIGHT_EM / 100,
            pause: item.pauses,
            displayType: item.display,
            label: item.label,
            // What the forked player puts in the marker's accessible name,
            // after the label. Left out it reads "Interaction. undefined".
            libraryTitle: item.typelabel || this.strings.types[item.type] || '',
            // Marked questions are posters whatever the row says. A question
            // the learner can decline to open is not a question the video can
            // refuse to continue past.
            ...(item.graded && item.pauses ? {displayType: 'poster'} : {}),
            action: {
                library: 'H5P.KaiivInteraction 1.0',
                params: {item: item},
            },
        };
    }

    /**
     * Send one answer to be marked, through the adapter.
     *
     * @param {Number|String} interactionid
     * @param {*} response
     * @returns {Promise<Object>} the verdict
     */
    submit(interactionid, response) {
        let pending;
        try {
            pending = Promise.resolve(this.config.answer(interactionid, response));
        } catch (error) {
            pending = Promise.reject(error);
        }

        return pending.then((reply) => {
            const verdict = reply || {};
            let answers = verdict.answers;
            // Accepted either way, because a server that passes the engine's
            // reply through sends a list and one that stores it as a column
            // sends a string. The renderers should not care which.
            if (typeof answers === 'string') {
                try {
                    answers = JSON.parse(answers);
                } catch (error) {
                    answers = [];
                }
            }
            const verdictOut = {
                ok: !!verdict.ok,
                error: verdict.error || '',
                correct: !!verdict.correct,
                revealed: !!verdict.revealed,
                // The engine calls it may_retry; Moodle's web service mayretry.
                mayretry: verdict.mayretry !== undefined
                    ? !!verdict.mayretry : !!verdict.may_retry,
                attempts: verdict.attempts || 0,
                answers: answers || [],
                feedback: verdict.feedback || '',
            };
            if (verdictOut.ok && typeof this.config.onAnswer === 'function') {
                this.config.onAnswer(interactionid, verdictOut);
            }
            return verdictOut;
        }).catch((error) => {
            Log.error('kaiiv: answer call failed', error);
            return undelivered();
        });
    }

    /**
     * Report where the playhead is, periodically and on the way out.
     */
    watchPlayhead() {
        // Listened to on the video, not on the player. The shim triggers these
        // on the H5P.Video instance, which is where upstream triggers them
        // too; upstream relies on H5P core bubbling them to the parent, and
        // the shim does not bubble.
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
                if (typeof this.config.onEnd === 'function') {
                    this.config.onEnd();
                }
            }
        });

        // Both events, because neither fires reliably alone: pagehide is
        // skipped when a mobile browser is backgrounded and killed, and
        // visibilitychange does not fire on some desktop navigations.
        // Sending twice is harmless when the server keeps the furthest point.
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
     * The fork's skip prevention guards the seek bar, and only that. Anybody
     * with a console can set video.currentTime directly, so the rule is
     * enforced here too, against the playhead rather than the control: at or
     * past the point and unanswered means go back to it.
     *
     * The server is still the record — an answer skipped this way is simply
     * never marked. This is what stops a learner reaching the end believing
     * they finished.
     */
    enforceDue() {
        if (!this.config.mustanswer || !this.instance || !this.instance.video) {
            return;
        }

        const at = this.instance.video.getCurrentTime();

        // `answered` is set on these same objects by interactions.js when the
        // server accepts an answer, so this reads the current state.
        const due = this.items.filter(
            (item) => item.pauses && !item.answered && item.start <= at);

        if (!due.length) {
            return;
        }

        // Earliest first: sending them back to the last one they passed would
        // let them skip the ones before it.
        const first = due.reduce((a, b) => (a.start <= b.start ? a : b));

        // A margin, because the playhead is sampled rather than continuous.
        if (at > first.start + 0.5) {
            this.instance.video.pause();
            // Through the fork's own seek, which resets its pointer to the
            // next interaction; forced, because its skip rule would otherwise
            // be consulted about a seek whose whole purpose is that rule.
            this.instance.seek(first.start, {force: true});
            // And told to draw what is there: the fork renders interactions
            // from its playback loop, which does not run while paused.
            this.instance.toggleInteractions(first.start);
        }
    }

    /**
     * @param {Boolean} finished
     * @param {Boolean} leaving whether the page is going away, in which case
     *        the adapter should use something that outlives it (sendBeacon)
     */
    report(finished, leaving) {
        this.lastReported = Date.now();
        if (typeof this.config.progress !== 'function') {
            return;
        }
        const state = {
            position: this.instance.video ? this.instance.video.getCurrentTime() : 0,
            finished: !!finished,
            leaving: !!leaving,
        };
        try {
            // Progress is advisory — the grade comes from the answers — so a
            // failure here must not interrupt the lesson.
            Promise.resolve(this.config.progress(state)).catch(() => null);
        } catch (error) {
            Log.warn('kaiiv: progress report failed', error);
        }
    }

    /**
     * Put the playhead back where the learner left it.
     */
    resume() {
        // Not past anything they have not answered: stopping just short means
        // the question arrives by playing into it, the way it did the first
        // time.
        let target = this.config.resumeat || 0;
        const unanswered = this.items
            .filter((item) => item.pauses && !item.answered && item.start < target)
            .map((item) => item.start);
        if (unanswered.length) {
            target = Math.max(0, Math.min(...unanswered) - 1);
        }

        // Below this, resuming skips an opening the learner has barely seen.
        if (target <= 5 || !this.instance.video) {
            return;
        }

        // Forced: the fork's skip rule measures against the furthest point
        // reached in this page load, which on arrival is zero.
        this.instance.video.on('ready', () => {
            this.instance.seek(target, {force: true});
        });
    }
}

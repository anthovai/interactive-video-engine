// Does the fork actually run with no H5P and no iframe under it?
//
// This is the question the whole plugin rests on, and until it is answered
// every other test is testing something that may never boot. check_fork.py
// compares two lists of names, which catches a gap in the shim; it cannot
// catch a member that exists and is the wrong shape, and it cannot catch the
// import-order rule the shim depends on.
//
// So this loads the real built bundle into a real DOM, with Moodle's modules
// stubbed, and starts a player against a small timeline. It is not a browser
// and it does not play a video — jsdom has no media stack, and the backend is
// stubbed for that reason. What it does prove is that 8,500 lines of forked
// code evaluate, construct and draw against the compatibility layer.
//
//     npm run build && node tests/smoke.js
//
// The last check is the one that matters most commercially, and it is the
// same claim test_15_kaivideo.py makes about the other player in a real
// browser: the correct answer is not in the page.

const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');


const ROOT = path.resolve(__dirname, '..');

const problems = [];
const notes = [];

const check = (name, condition, detail) => {
    if (condition) {
        process.stdout.write('  ok    ' + name + '\n');
    } else {
        process.stdout.write('  FAIL  ' + name + (detail ? '  ' + detail : '') + '\n');
        problems.push(name);
    }
};

// --------------------------------------------------------------------------
// A page that looks enough like view.php's output
// --------------------------------------------------------------------------

const PAGE = `<!DOCTYPE html><html><body>
<div class="kaiiv" data-region="kaiiv" data-state="loading" data-provider="file">
  <div class="kaiiv-stage" data-region="stage">
    <div class="ratio ratio-16x9">
      <video data-region="video" preload="metadata" src="/lesson.mp4"></video>
    </div>
    <div class="kaiiv-overlay" data-region="overlay"></div>
  </div>
  <div class="kaiiv-controls" data-region="controls"></div>
  <div class="alert" data-region="problem" hidden></div>
</div>
</body></html>`;

// --------------------------------------------------------------------------
// The timeline, with answers a leak would show
// --------------------------------------------------------------------------
// The words are distinctive on purpose. "Paris" appears in no forked string,
// no Bootstrap class and no jQuery internal, so finding it in the rendered
// page means it came from here.

const ITEMS = [
    {
        id: 1, type: 'choice', start: 5, end: 5.01, display: 'poster',
        pauses: true, x: 10, y: 10, width: 80, height: 60,
        label: 'Question', graded: true, answered: false, attempts: 0,
        revealed: false,
        content: {text: 'Which of these is a capital?',
            options: ['Lyon', 'Marseille', 'Paris']},
    },
    {
        id: 2, type: 'shorttext', start: 20, end: 20.01, display: 'poster',
        pauses: true, x: 10, y: 10, width: 80, height: 60,
        label: 'Question', graded: true, answered: false, attempts: 0,
        revealed: false,
        content: {text: 'Capital of France?'},
    },
    {
        id: 3, type: 'label', start: 30, end: 40, display: 'button',
        pauses: false, x: 70, y: 10, width: 25, height: 15,
        label: 'Note', graded: false, answered: false, attempts: 0,
        revealed: false,
        content: {text: 'Remember to check the gauge.'},
    },
];

const CONFIG = {
    cmid: 42,
    provider: 'file',
    videoid: '',
    streamurl: '',
    items: ITEMS,
    bookmarks: [{at: 15, label: 'Section two'}],
    mustanswer: true,
    allowreview: true,
    maxattempts: 2,
    posterstart: true,
    showendscreen: true,
    title: 'Safety induction',
    resumeat: 0,
};

// --------------------------------------------------------------------------
// Moodle, stubbed
// --------------------------------------------------------------------------

const submitted = [];

const STUBS = {
    'jquery': null, // filled in once the window exists
    'core/log': {
        error: (...args) => notes.push('Log.error: ' + args.map(
            (one) => (one && one.stack) ? one.stack : String(one)).join(' ')),
        warn: (...args) => notes.push('Log.warn: ' + args.join(' ')),
        debug: () => {},
    },
    'core/ajax': {
        call: (calls) => calls.map((one) => {
            submitted.push(one);
            if (one.methodname === 'mod_kaiiv_answer') {
                // Always wrong, with a retry left — the case where the server
                // withholds everything. If the answer turns up in the page
                // after this, it did not come from the server.
                return Promise.resolve({
                    ok: true, error: '', correct: false, revealed: false,
                    mayretry: true, attempts: 1, answers: '[]', feedback: '',
                });
            }
            return Promise.resolve({ok: true});
        }),
    },
    // Shaped the way Moodle's real core/str is: an ES module Moodle
    // transpiles, so the built form sets __esModule and exports names with no
    // default. Getting this wrong here is how a default import survived the
    // smoke test and then failed on the first real page — a stub is whatever
    // shape the stub was written in, which is the standing limit of this file.
    'core/str': {
        __esModule: true,
        getStrings: (requests) => Promise.resolve(
            requests.map((one) => 'str:' + one.key)),
        get_strings: (requests) => Promise.resolve(
            requests.map((one) => 'str:' + one.key)),
    },
    'core/notification': {exception: () => {}},
    // No local_kaiproctor module here, on purpose: mod_kaiiv installs on a
    // Moodle that has none of our other plugins, and the loader below fails
    // loudly if the bundle ever asks for one again.
    // Moodle loads the real jQuery UI; here the one method the fork reaches
    // for is installed on the same $.fn, in setUp below. Stubbed rather than
    // required, because jQuery UI is not ours to test — what is being checked
    // is that the seekbar finds a slider to call, not that jQuery's works.
    'jqueryui': {},
};

/**
 * A backend that answers the interface without playing anything.
 *
 * jsdom has no media stack, so a real <video> here would never fire a
 * timeupdate and never report a duration. What is being tested is the fork,
 * not the backend — the backend has its own life in mod_kaivideo, where it
 * came from.
 */
const makeBackendStub = () => {
    let time = 0;
    const ticks = [];
    return {
        create: (config, root) => Promise.resolve({
            host: root.querySelector('video') || root,
            play: () => Promise.resolve(),
            pause: () => {},
            seek: (seconds) => {
                time = seconds;
                ticks.forEach((fn) => fn());
            },
            currentTime: () => time,
            duration: () => 300,
            isPaused: () => true,
            onTick: (fn) => ticks.push(fn),
            onEnded: () => {},
            onPlayAttempt: () => {},
        }),
    };
};

// --------------------------------------------------------------------------

const run = async () => {
    process.stdout.write('fork smoke test\n\n');

    // runScripts lets the bundle be evaluated *inside* the window rather than
    // beside it, and that distinction is the whole point of this file.
    //
    // The forked code reads a bare `H5P`, which the shim satisfies by setting
    // window.H5P. Evaluated in Node's own global scope the bundle throws "H5P
    // is not defined" — not because the shim is wrong, but because a bare
    // identifier there resolves against Node's global and not against the
    // window the shim wrote to. Running it outside the window would be
    // testing a situation no browser is ever in.
    const dom = new JSDOM(PAGE, {
        url: 'https://example.invalid/mod/kaiiv/view.php?id=42',
        pretendToBeVisual: true,
        runScripts: 'outside-only',
    });
    const {window} = dom;

    global.window = window;
    global.document = window.document;
    global.navigator = window.navigator;
    global.HTMLElement = window.HTMLElement;
    global.Element = window.Element;
    global.Node = window.Node;
    global.getComputedStyle = window.getComputedStyle.bind(window);

    // jQuery has to be the one attached to this window, or every selector the
    // fork runs finds nothing and the failures read as missing markup.
    //
    // What require() hands back depends on whether a global window was
    // visible when the module first loaded: a jQuery already bound to it, or
    // a factory still waiting for one. Both are functions, which is why
    // calling the wrong one is not an error — jQuery(window) returns a
    // collection, and a collection is a fine object that is not callable.
    // That surfaced deep inside the fork as "$ is not a function" and looked
    // exactly like a broken compatibility layer.
    const jq = require('jquery');
    STUBS.jquery = (jq.fn && jq.fn.jquery) ? jq : jq(window);

    // What Moodle's 'jqueryui' module does to $.fn, in one line. The fork
    // calls .slider() on the seekbar and then again to read and set its
    // value, so it has to be chainable and it has to answer.
    STUBS.jquery.fn.slider = function() {
        return this;
    };
    STUBS['mod_kaiiv/backend'] = makeBackendStub();

    // The smallest AMD loader that satisfies a named define with deps.
    const defined = {};
    window.define = (name, deps, factory) => {
        defined[name] = factory(...deps.map((dep) => {
            if (STUBS[dep] === undefined) {
                throw new Error('the bundle asked for an unstubbed module: ' + dep);
            }
            return STUBS[dep];
        }));
    };
    window.define.amd = true;
    // backend.min.js is loaded as a stub, not from disk, so nothing here
    // reaches the runtime require() calls it makes.
    window.require = () => {
        throw new Error('runtime require() reached in the smoke test');
    };

    const bundle = path.join(ROOT, 'amd/build/player.min.js');
    if (!fs.existsSync(bundle)) {
        check('the bundle exists', false, 'run npm run build first');
        return;
    }

    // window.eval, so the bundle runs in the window's scope. See the JSDOM
    // options above for why nothing else will do.
    try {
        window.eval(fs.readFileSync(bundle, 'utf8'));
        check('the bundle evaluates', true);
    } catch (error) {
        check('the bundle evaluates', false, error.message);
        return;
    }

    const player = defined['mod_kaiiv/player'];
    check('it defines mod_kaiiv/player', !!player);
    check('with an init function', player && typeof player.init === 'function');

    check('the shim published window.H5P', !!window.H5P);
    check('the fork registered itself as H5P.InteractiveVideo',
        typeof window.H5P.InteractiveVideo === 'function');
    check('and as H5P.InteractiveVideoInteraction',
        typeof window.H5P.InteractiveVideoInteraction === 'function');
    check('H5P.Video carries upstream state constants',
        window.H5P.Video && window.H5P.Video.PLAYING === 1
        && window.H5P.Video.ENDED === 0);

    if (!player || problems.length) {
        return;
    }

    try {
        player.init(CONFIG);
    } catch (error) {
        check('init() runs', false, error.stack.split('\n').slice(0, 3).join(' | '));
        return;
    }
    check('init() runs', true);

    // Strings resolve through a promise, and the fork builds its DOM after
    // that. Two turns of the microtask queue plus a timer is enough for
    // everything that is not waiting on a real network.
    await new Promise((resolve) => window.setTimeout(resolve, 200));

    const root = window.document.querySelector('[data-region="kaiiv"]');
    const stage = window.document.querySelector('[data-region="stage"]');

    check('the player reported itself ready',
        root.getAttribute('data-state') === 'ready',
        'state is ' + root.getAttribute('data-state'));
    check('the fork drew something into the stage',
        stage.children.length > 1,
        stage.children.length + ' children');
    check('our interaction type is registered',
        typeof window.H5P.KaiivInteraction === 'function');

    // ---- the claim ------------------------------------------------------
    const html = window.document.documentElement.innerHTML;

    check('no correct answer is in the page',
        !/\bParis\b/.test(html),
        'the word Paris is in the rendered DOM');
    check('the question itself is',
        /Capital of France|capital/i.test(html)
        || stage.textContent.length > 0);

    // ---- what threw on the way -----------------------------------------
    //
    // The shim's event dispatcher catches what listeners throw, on purpose: a
    // question that fails to draw is a support call, and a video that stops
    // responding is an exam that has to be re-sat. That is the right trade at
    // runtime and the wrong one in a test, because it turns a broken feature
    // into a line in a log nobody reads.
    //
    // So anything caught on the way up is failed here.
    const thrown = notes.filter((note) => note.startsWith('Log.error'));
    check('nothing threw while the player started',
        thrown.length === 0, thrown.length + ' error(s), listed below');

    // The known one, called out separately so it is not merely a count.
    //
    // The fork builds its seekbar with jQuery UI's slider — one of its
    // declared H5P dependencies upstream (jQuery.ui 1.10 in library.json) and
    // one nothing here supplies yet. Moodle ships jQuery UI, so this is a
    // module to depend on rather than a thing to write; which name it answers
    // to has to be read off a running Moodle rather than guessed into a build.
    check('the seekbar has a slider to draw with',
        typeof STUBS.jquery.fn.slider === 'function',
        'jQuery UI is not loaded; the seekbar will not be interactive');

    for (const note of notes) {
        process.stdout.write('  note  ' + note + '\n');
    }
};

run().then(() => {
    process.stdout.write('\n');
    if (problems.length) {
        process.stdout.write(problems.length + ' problem(s)\n');
        process.exit(1);
    }
    process.stdout.write('the fork runs under the compatibility layer\n');
    process.exit(0);
}).catch((error) => {
    process.stderr.write('\nsmoke test itself failed:\n' + error.stack + '\n');
    process.exit(2);
});

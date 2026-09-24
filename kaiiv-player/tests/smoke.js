// Load dist/kaiiv-player.js the way a customer's page does, in jsdom.
//
//     node tests/smoke.js
//
// A plain <script> build on a page with no Moodle, no jQuery, no Bootstrap and
// no AMD loader: that is the situation it is for, and nothing else here tests
// it. It checks that the global appears, that a player starts against an
// adapter, that answering goes through the adapter and nowhere else, and that
// nothing the browser holds is an answer.
//
// It does not play a video — jsdom has no media stack — so the <video> is
// given the properties a loaded one has. tests/browser.py drives a real
// browser against examples/server for the rest.

const fs = require('fs');
const path = require('path');
const {JSDOM} = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const problems = [];
const errors = [];

const check = (name, condition, detail) => {
    process.stdout.write((condition ? '  ok    ' : '  FAIL  ') + name
        + (!condition && detail ? '  ' + detail : '') + '\n');
    if (!condition) {
        problems.push(name);
    }
};

// What a server passes through from the engine's /timeline: no answers. That
// the engine never puts one in is tested where it is decided, in
// kaiiv-service/tests/test_contract.py; tests/browser.py checks the page.
const ITEMS = [
    {id: 11, type: 'choice', start: 5, end: 5, display: 'poster', pauses: true,
        x: 10, y: 10, width: 80, height: 60, label: 'Q1', graded: true,
        answered: false, attempts: 0, revealed: false,
        content: {text: 'Which of these is a capital?', options: ['Lyon', 'Marseille', 'Paris']}},
    {id: 12, type: 'label', start: 30, end: 40, display: 'button', pauses: false,
        x: 70, y: 10, width: 25, height: 15, label: 'Note', graded: false,
        answered: false, attempts: 0, revealed: false,
        content: {text: 'Remember to check the gauge.'}},
];

const pretendLoaded = (video) => {
    let time = 0;
    let paused = true;
    Object.defineProperties(video, {
        readyState: {get: () => 4},
        duration: {get: () => 300},
        paused: {get: () => paused},
        currentTime: {get: () => time, set: (value) => {
            time = value;
        }},
        buffered: {get: () => ({length: 0})},
    });
    video.play = () => {
        paused = false;
        return Promise.resolve();
    };
    video.pause = () => {
        paused = true;
    };
};

const run = async () => {
    process.stdout.write('standalone smoke test\n\n');

    const bundle = path.join(ROOT, 'dist/kaiiv-player.js');
    const css = path.join(ROOT, 'dist/kaiiv-player.css');
    check('dist/kaiiv-player.js exists', fs.existsSync(bundle), 'run npm run build');
    check('dist/kaiiv-player.css exists', fs.existsSync(css), 'run npm run build');
    if (problems.length) {
        return;
    }

    const dom = new JSDOM('<!DOCTYPE html><html><body><div id="lesson"></div></body></html>', {
        url: 'https://customer.example/lesson/1',
        pretendToBeVisual: true,
        runScripts: 'outside-only',
    });
    const {window} = dom;
    window.console.error = (...args) => errors.push(args.map(String).join(' '));

    try {
        window.eval(fs.readFileSync(bundle, 'utf8'));
        check('the bundle evaluates on a page with nothing else on it', true);
    } catch (error) {
        check('the bundle evaluates on a page with nothing else on it', false, error.message);
        return;
    }

    const api = window.KaiivPlayer;
    check('it defines window.KaiivPlayer', !!api);
    check('with create()', api && typeof api.create === 'function');
    check('and a version', api && /^\d+\.\d+\.\d+/.test(api.version), api && api.version);
    check('it put no jQuery on the page', !window.jQuery && !window.$);

    let refused = null;
    try {
        await api.create('#lesson', {video: {src: '/a.mp4'}, items: []});
    } catch (error) {
        refused = error;
    }
    check('a player with nowhere to send answers is refused',
        refused && /answer is required/.test(refused.message));
    // That refusal is logged, on purpose; it is not one of the errors the
    // last check is looking for.
    errors.length = 0;

    const calls = [];
    const progress = [];
    const created = api.create('#lesson', {
        video: {provider: 'file', src: '/lessons/intro.mp4'},
        items: ITEMS,
        title: 'Safety induction',
        lang: 'th',
        answer: (id, response) => {
            calls.push({id, response});
            return Promise.resolve({ok: true, correct: true, revealed: true,
                may_retry: false, attempts: 1, answers: [2], feedback: 'Well done'});
        },
        progress: (state) => progress.push(state),
    });

    // The element is built synchronously inside create(), and the backend is
    // by then waiting for its metadata — which is the path a learner's first
    // visit takes, before the file is in any cache. So the metadata arrives
    // afterwards here too, as an event.
    const video = window.document.querySelector('#lesson video');
    check('it built a <video> with the source', video
        && video.getAttribute('src') === '/lessons/intro.mp4');
    if (video) {
        pretendLoaded(video);
        video.dispatchEvent(new window.Event('loadedmetadata'));
    }

    let handle;
    try {
        handle = await created;
    } catch (error) {
        check('create() resolves', false, error.message);
        return;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 200));

    const root = window.document.querySelector('#lesson [data-region="kaiiv"]');
    check('create() resolves with the root', handle && handle.root === root);
    check('the player reported itself ready', root && root.getAttribute('data-state') === 'ready');
    check('the fork drew its controls', !!window.document.querySelector('#lesson .h5p-controls'));
    check('the video element survived the fork emptying the stage',
        window.document.querySelector('#lesson video') === video);
    const playButton = window.document.querySelector('#lesson .h5p-controls-left [role="button"]');
    check('the Thai strings were used', playButton
        && /เล่น/.test(playButton.getAttribute('aria-label') || ''),
        playButton && playButton.getAttribute('aria-label'));

    // Bring the question up the way the due rule does — through the fork's
    // own seek, then asking it to draw what is at that second — and answer
    // it through the card, as a learner would.
    handle.instance.seek(5, {force: true});
    handle.instance.toggleInteractions(5);
    await new Promise((resolve) => window.setTimeout(resolve, 100));
    // jsdom lays nothing out, so the player measures itself as zero wide and
    // takes the fork's compact mode — the one a phone gets — where a question
    // is a button that opens it in the dialog. Pressed, as on a phone.
    const opener = window.document.querySelector(
        '#lesson .h5p-interaction.h5p-kaiivinteraction-interaction');
    if (opener && !window.document.querySelector('#lesson [data-option="2"]')) {
        opener.click();
        await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    const option = window.document.querySelector('#lesson [data-option="2"]');
    check('the question was drawn', !!option);
    if (option) {
        option.click();
        await new Promise((resolve) => window.setTimeout(resolve, 100));
    }
    check('answering went through the adapter', calls.length === 1
        && calls[0].id === 11 && JSON.stringify(calls[0].response) === '[2]',
        JSON.stringify(calls));
    check('and the verdict was shown', /ถูกต้อง/.test(window.document.body.textContent));

    check('nothing was reported as an error', errors.length === 0, errors.join(' | '));
};

run().then(() => {
    process.stdout.write(problems.length
        ? `\n${problems.length} problem(s)\n` : '\nthe standalone build works on a bare page\n');
    process.exit(problems.length ? 1 : 0);
}, (error) => {
    process.stdout.write('\nthe smoke test itself failed: ' + error.stack + '\n');
    process.exit(1);
});

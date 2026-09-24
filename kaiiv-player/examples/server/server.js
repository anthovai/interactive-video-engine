// The smallest server that runs a KAISER interactive video lesson.
//
//     KAIIV_API_KEY=<the engine's key> node server.js
//     open http://127.0.0.1:8200/
//
// Node 18 or later, no packages. It is an example to read and copy from, not a
// product: one lesson, answers kept in a JSON file, a learner told apart by a
// cookie. What it does show, and what any system that uses the player has to
// do the same way, is where each thing lives:
//
//   the engine's key       here, in the environment. Never in the page.
//   the answers            here, in data.json. Never in the page.
//   the marking            the engine, asked by this server. Never the page.
//   the learner's record   here. The engine keeps nothing.
//
// The page gets the timeline the engine chose to let this learner see, and a
// URL to post answers to. That is the whole of what the browser is trusted
// with, and it is why a learner with the developer tools open learns nothing.

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const http = require('http');
const path = require('path');

const PORT = Number(process.env.PORT || 8200);
const HOST = process.env.HOST || '127.0.0.1';
const ENGINE = (process.env.KAIIV_ENGINE_URL || 'http://127.0.0.1:9200').replace(/\/+$/, '');
const KEY = process.env.KAIIV_API_KEY || '';
const DATA = process.env.KAIIV_DATA || path.join(__dirname, 'data.json');
const MEDIA = path.join(__dirname, 'media');
const DIST = path.resolve(__dirname, '../../dist');
const CONTRACT = '1.0';

if (!KEY) {
    process.stderr.write('set KAIIV_API_KEY to the key the engine was started with\n');
    process.exit(1);
}

// ---------------------------------------------------------------------------
// Talking to the engine
// ---------------------------------------------------------------------------

/**
 * POST to the engine. Resolves with its JSON, including its named refusals
 * ({ok: false, error: 'bad_authoring', detail: ...}), which are passed on
 * rather than flattened: "no option is marked correct" is something an author
 * can fix, and "error" is not.
 */
const engine = async (route, body) => {
    let response;
    try {
        response = await fetch(ENGINE + route, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Proctor-Key': KEY},
            body: JSON.stringify({contract: CONTRACT, ...body}),
        });
    } catch (error) {
        return {ok: false, error: 'unreachable', detail: String(error.message || error)};
    }
    if (response.status === 401) {
        return {ok: false, error: 'bad_key', detail: 'the engine refused our key'};
    }
    try {
        return await response.json();
    } catch (error) {
        return {ok: false, error: 'malformed', detail: 'status ' + response.status};
    }
};

// ---------------------------------------------------------------------------
// The record: one lesson, its interactions, and what each learner did
// ---------------------------------------------------------------------------

const load = () => (fs.existsSync(DATA)
    ? JSON.parse(fs.readFileSync(DATA, 'utf8')) : {lessons: {}, responses: [], progress: {}});

const save = (data) => {
    const temporary = DATA + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify(data, null, 2));
    fs.renameSync(temporary, DATA);
};

/**
 * What this learner has done, in the shape the engine reads: interaction id
 * to the latest response, whether it was right, and how many attempts so far.
 */
const seenBy = (data, lessonId, learner) => {
    const seen = {};
    data.responses
        .filter((r) => r.lesson === lessonId && r.learner === learner)
        .forEach((r) => {
            const key = String(r.interaction);
            seen[key] = {
                response: r.response,
                correct: r.correct,
                attempts: (seen[key] ? seen[key].attempts : 0) + 1,
                everCorrect: (seen[key] && seen[key].everCorrect) || r.correct,
            };
        });
    return seen;
};

/**
 * Add one interaction to a lesson, the way an authoring screen would.
 *
 * The authored form has the answers in it — `*Paris*` in a gap sentence, a
 * ticked option — and it is sent to the engine and never stored. What comes
 * back is two halves, content and answers, and they are stored apart so that
 * nothing that reads the content can reach the answers by accident.
 */
const author = async (lessonId, fields) => {
    const split = await engine('/author', {type: fields.type, authored: fields.authored});
    if (!split.ok) {
        return split;
    }
    const data = load();
    const lesson = data.lessons[lessonId];
    lesson.nextId = lesson.nextId || 1;
    const id = lesson.nextId++;
    lesson.interactions.push({
        id: id,
        type: fields.type,
        start: fields.start,
        // One that pauses ends when it is answered; anything else stays up for
        // as long as the author said, or five seconds.
        end: split.pauses ? fields.start : (fields.end > fields.start ? fields.end : fields.start + 5),
        display: split.graded && split.pauses ? 'poster' : (fields.display || 'poster'),
        pauses: !!split.pauses,
        x: fields.x ?? 20, y: fields.y ?? 20, width: fields.width ?? 60, height: fields.height ?? 40,
        label: fields.label || '',
        content: split.content,
        answers: split.answers,
        feedback: fields.feedback || '',
    });
    save(data);
    return {ok: true, id: id};
};

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------

const TYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
    '.mp4': 'video/mp4', '.webm': 'video/webm', '.woff': 'font/woff', '.woff2': 'font/woff2',
    '.ttf': 'font/ttf', '.eot': 'application/vnd.ms-fontobject', '.png': 'image/png',
    '.txt': 'text/plain; charset=utf-8',
};

const send = (res, status, body, type) => {
    res.writeHead(status, {
        'Content-Type': type || 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff',
    });
    res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
};

/**
 * A file under a directory, with Range support: a browser seeking in a video
 * asks for part of it, and a server that answers with the whole file every
 * time makes the seekbar useless.
 */
const serveFile = (req, res, root, relative) => {
    const file = path.resolve(root, '.' + path.posix.normalize('/' + relative));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
        return send(res, 404, {ok: false, error: 'not_found'});
    }
    const size = fs.statSync(file).size;
    const type = TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
    const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
    if (range) {
        const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
        const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
        if (start > end || start >= size) {
            res.writeHead(416, {'Content-Range': `bytes */${size}`});
            return res.end();
        }
        res.writeHead(206, {
            'Content-Type': type, 'Accept-Ranges': 'bytes',
            'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': end - start + 1,
        });
        return fs.createReadStream(file, {start, end}).pipe(res);
    }
    res.writeHead(200, {'Content-Type': type, 'Accept-Ranges': 'bytes', 'Content-Length': size});
    return fs.createReadStream(file).pipe(res);
};

const readBody = (req) => new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
        raw += chunk;
        // An answer is a few hundred bytes. Anything this size is not one.
        if (raw.length > 64 * 1024) {
            reject(new Error('too large'));
            req.destroy();
        }
    });
    req.on('end', () => {
        try {
            resolve(raw ? JSON.parse(raw) : {});
        } catch (error) {
            reject(error);
        }
    });
});

/**
 * Who this is. A cookie, because this is an example; a real system already
 * knows who is signed in and uses that instead.
 */
const learnerOf = (req, res) => {
    const match = /(?:^|;\s*)kaiiv_learner=([a-f0-9-]{36})/.exec(req.headers.cookie || '');
    if (match) {
        return match[1];
    }
    const id = crypto.randomUUID();
    res.setHeader('Set-Cookie', `kaiiv_learner=${id}; Path=/; HttpOnly; SameSite=Lax`);
    return id;
};

/** </script> in a string would close the tag it is inlined into. */
const inlineJson = (value) => JSON.stringify(value).replace(/</g, '\\u003c');

const lessonPage = (lesson, items, resumeat) => `<!DOCTYPE html>
<html lang="${lesson.lang || 'th'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${lesson.title.replace(/[<&]/g, '')}</title>
<link rel="stylesheet" href="/player/kaiiv-player.css">
<style>
  body { margin: 0; background: #f5f6f8; font-family: system-ui, sans-serif; }
  main { max-width: 56rem; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.5rem; }
  #score { margin-top: 1rem; color: #444; }
</style>
</head>
<body>
<main>
  <h1>${lesson.title.replace(/[<&]/g, '')}</h1>
  <div id="lesson"></div>
  <p id="score"></p>
</main>
<script src="/player/kaiiv-player.js"></script>
<script>
  // Everything the page is given: what the engine let this learner see.
  const items = ${inlineJson(items)};
  const post = (url, body) => fetch(url, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body), credentials: 'same-origin',
  }).then((r) => r.json());

  KaiivPlayer.create('#lesson', {
      video: ${inlineJson(lesson.video)},
      items: items,
      title: ${inlineJson(lesson.title)},
      lang: ${inlineJson(lesson.lang || 'th')},
      mustanswer: ${lesson.rules.mustanswer !== false},
      resumeat: ${Number(resumeat) || 0},
      answer: (id, response) => post('/api/lessons/${lesson.id}/answer',
          {interaction: id, response: response}),
      progress: ({position, finished, leaving}) => {
          const body = JSON.stringify({position, finished});
          if (leaving && navigator.sendBeacon) {
              navigator.sendBeacon('/api/lessons/${lesson.id}/progress',
                  new Blob([body], {type: 'application/json'}));
              return;
          }
          return post('/api/lessons/${lesson.id}/progress', {position, finished});
      },
      onAnswer: () => fetch('/api/lessons/${lesson.id}/score', {credentials: 'same-origin'})
          .then((r) => r.json())
          .then((s) => { document.getElementById('score').textContent =
              s.ok ? 'คะแนน ' + s.correct + ' / ' + s.total : ''; }),
  });
</script>
</body>
</html>
`;

const routes = async (req, res) => {
    const url = new URL(req.url, 'http://local');
    const parts = url.pathname.split('/').filter(Boolean);

    if (req.method === 'GET' && parts[0] === 'player') {
        return serveFile(req, res, DIST, parts.slice(1).join('/'));
    }
    if (req.method === 'GET' && parts[0] === 'media') {
        return serveFile(req, res, MEDIA, parts.slice(1).join('/'));
    }

    const data = load();
    const lessonId = parts[0] === 'api' ? parts[2] : (parts[1] || Object.keys(data.lessons)[0]);
    const lesson = data.lessons[lessonId];

    // The lesson page. The timeline is fetched here, on the server, and put
    // into the page. The page never asks for it: a page that could request a
    // timeline is a page a learner can request one from with whatever
    // parameters they like.
    if (req.method === 'GET' && (parts.length === 0 || parts[0] === 'lesson')) {
        if (!lesson) {
            return send(res, 404, 'no lesson; run: node seed.js', 'text/plain; charset=utf-8');
        }
        const learner = learnerOf(req, res);
        const timeline = await engine('/timeline', {
            interactions: lesson.interactions,
            seen: seenBy(data, lessonId, learner),
            rules: lesson.rules,
        });
        if (!timeline.ok) {
            // Refused rather than played without its questions. A video that
            // plays with nothing on it looks like it worked, and a learner
            // watches it to the end believing they are finished.
            return send(res, 503, 'the engine is unavailable: ' + timeline.error,
                'text/plain; charset=utf-8');
        }
        const resumeat = (data.progress[lessonId + ':' + learner] || {}).furthest || 0;
        return send(res, 200, lessonPage(lesson, timeline.items, resumeat), TYPES['.html']);
    }

    if (parts[0] !== 'api' || parts[1] !== 'lessons' || !lesson) {
        return send(res, 404, {ok: false, error: 'not_found'});
    }
    const learner = learnerOf(req, res);

    // An answer. Marked by the engine, recorded here, and only what the engine
    // chose to release goes back.
    if (req.method === 'POST' && parts[3] === 'answer') {
        let body;
        try {
            body = await readBody(req);
        } catch (error) {
            return send(res, 400, {ok: false, error: 'bad_request'});
        }
        const interaction = lesson.interactions.find((i) => i.id === Number(body.interaction));
        if (!interaction) {
            return send(res, 404, {ok: false, error: 'no_such_interaction'});
        }
        const before = seenBy(data, lessonId, learner)[String(interaction.id)];
        const verdict = await engine('/judge', {
            type: interaction.type,
            content: interaction.content,
            answers: interaction.answers,
            feedback: interaction.feedback,
            response: body.response,
            // What the engine needs to refuse an answer past the last attempt,
            // or after a correct one. It is told, because it keeps nothing.
            attempts: before ? before.attempts : 0,
            answered_correctly: !!(before && before.everCorrect),
            rules: lesson.rules,
        });
        if (!verdict.ok) {
            return send(res, 200, {ok: false, error: verdict.error});
        }
        data.responses.push({
            lesson: lessonId, learner: learner, interaction: interaction.id,
            response: verdict.store, correct: !!verdict.correct,
            attempt: verdict.attempts, at: new Date().toISOString(),
        });
        save(data);
        return send(res, 200, {
            ok: true, correct: verdict.correct, revealed: verdict.revealed,
            may_retry: verdict.may_retry, attempts: verdict.attempts,
            answers: verdict.answers, feedback: verdict.feedback,
        });
    }

    // How far they got. Advisory: the grade comes from the answers.
    if (req.method === 'POST' && parts[3] === 'progress') {
        let body;
        try {
            body = await readBody(req);
        } catch (error) {
            return send(res, 400, {ok: false, error: 'bad_request'});
        }
        const key = lessonId + ':' + learner;
        const record = data.progress[key] || {furthest: 0, finished: false};
        // The furthest point, not the last reported: a learner who scrubs back
        // to rewatch has not undone what they watched.
        record.furthest = Math.max(record.furthest, Number(body.position) || 0);
        record.finished = record.finished || !!body.finished;
        data.progress[key] = record;
        save(data);
        return send(res, 200, {ok: true});
    }

    if (req.method === 'GET' && parts[3] === 'score') {
        return send(res, 200, await engine('/score', {
            interactions: lesson.interactions,
            seen: seenBy(data, lessonId, learner),
        }));
    }

    return send(res, 404, {ok: false, error: 'not_found'});
};

module.exports = {author, load, save, engine};

if (require.main === module) {
    http.createServer((req, res) => {
        routes(req, res).catch((error) => {
            process.stderr.write(String(error.stack || error) + '\n');
            send(res, 500, {ok: false, error: 'server_error'});
        });
    }).listen(PORT, HOST, () => {
        process.stdout.write(`lesson at http://${HOST}:${PORT}/  (engine ${ENGINE})\n`);
    });
}

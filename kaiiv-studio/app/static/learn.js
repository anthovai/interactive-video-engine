// The learner's page: the player, wired to this studio's API.
//
// Everything the page knows came from the server when it was built — the
// timeline the engine chose for this learner — and everything it sends goes
// back to the server, which asks the engine. The page never talks to the
// engine and has no key to talk to it with.
(function() {
    'use strict';

    var script = document.currentScript;
    var lesson = script.getAttribute('data-lesson');
    var csrf = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    var config = JSON.parse(document.getElementById('lesson-config').textContent);
    var scoreLine = document.getElementById('score');

    var post = function(path, body) {
        return fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
            body: JSON.stringify(body)
        }).then(function(response) {
            return response.json();
        });
    };

    var showScore = function() {
        fetch('/api/lessons/' + lesson + '/score', {credentials: 'same-origin'})
            .then(function(response) { return response.json(); })
            .then(function(result) {
                if (result.ok && result.total) {
                    scoreLine.textContent = 'คะแนน ' + result.correct + ' / ' + result.total;
                }
            })
            .catch(function() { return null; });
    };

    config.answer = function(id, response) {
        return post('/api/lessons/' + lesson + '/answer', {interaction: id, response: response});
    };
    config.progress = function(state) {
        var body = {position: state.position, finished: state.finished};
        if (state.leaving && navigator.sendBeacon) {
            // A beacon cannot carry headers, so the token goes in the body.
            body.csrf = csrf;
            navigator.sendBeacon('/api/lessons/' + lesson + '/progress',
                new Blob([JSON.stringify(body)], {type: 'application/json'}));
            return null;
        }
        return post('/api/lessons/' + lesson + '/progress', body);
    };
    config.onAnswer = showScore;

    window.KaiivPlayer.create('#lesson', config).catch(function(error) {
        document.getElementById('lesson').textContent =
            'เปิดตัวเล่นไม่ได้: ' + (error && error.message ? error.message : error);
    });
    showScore();
})();

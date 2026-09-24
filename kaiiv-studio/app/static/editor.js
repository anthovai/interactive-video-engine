// The question editor: show the fields the chosen type has, and let the
// teacher take the time from the preview instead of typing it.
(function() {
    'use strict';

    var type = document.getElementById('type');
    var form = document.getElementById('interaction');
    var preview = document.getElementById('preview');

    // Fields are hidden, not removed: a teacher who picks the wrong type and
    // types a question into it keeps what they typed when they switch back.
    var toggle = function() {
        form.querySelectorAll('[data-types]').forEach(function(node) {
            var shown = node.getAttribute('data-types').split(' ').indexOf(type.value) !== -1;
            node.hidden = !shown;
        });
    };
    type.addEventListener('change', toggle);
    toggle();

    if (preview) {
        // A stream needs attaching; a file is already the element's src.
        if (preview.getAttribute('data-provider') === 'hls') {
            var src = preview.getAttribute('data-src');
            if (preview.canPlayType('application/vnd.apple.mpegurl')) {
                preview.src = src;
            } else if (window.Hls && window.Hls.isSupported()) {
                var hls = new window.Hls();
                hls.loadSource(src);
                hls.attachMedia(preview);
            }
        }
        var use = document.getElementById('usetime');
        if (use) {
            use.addEventListener('click', function() {
                document.getElementById('starttime').value = (Math.round(preview.currentTime * 10) / 10).toString();
            });
        }
        document.querySelectorAll('[data-seek]').forEach(function(button) {
            button.addEventListener('click', function() {
                preview.currentTime = parseFloat(button.getAttribute('data-seek'));
                preview.pause();
            });
        });
    }
})();

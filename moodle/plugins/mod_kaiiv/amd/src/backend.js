// A stream on the editing screen's preview.
//
// The player's own video backends are in kaiiv-player/src/backend.js and are
// bundled into player.min.js. This is the one piece of them edit.php needs on
// its own — the preview is not taking the lesson, keeps the browser's own
// controls, and needs none of the rest — so it stays a small AMD module
// rather than loading the whole player to show a video.
//
// Plain AMD with no imports, so a copy into amd/build is a correct build for
// it; see tools/build-plain-amd.js.
define([], function() {

    /**
     * Put an HLS stream on a <video>, with the browser's own support where it
     * has it and Moodle's video.js where it does not.
     *
     * @param {HTMLVideoElement} element
     * @param {String} url the .m3u8
     * @return {Promise}
     */
    var attach = function(element, url) {
        var native = element.canPlayType('application/vnd.apple.mpegurl');
        if (native === 'probably' || native === 'maybe') {
            element.src = url;
            return Promise.resolve(element);
        }

        return new Promise(function(resolve, reject) {
            require(['media_videojs/video-lazy'], function(videojs) {
                var player = videojs(element, {controls: true, fluid: false});
                player.src({src: url, type: 'application/x-mpegURL'});
                resolve(element);
            }, function() {
                reject(new Error('videojs_unavailable'));
            });
        });
    };

    return {
        /**
         * @param {String} selector
         * @param {String} url the .m3u8
         * @return {Promise}
         */
        attachStream: function(selector, url) {
            var element = document.querySelector(selector);
            return element ? attach(element, url) : Promise.resolve(null);
        }
    };
});

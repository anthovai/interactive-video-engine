// One playhead interface over four very different players.
//
// The rest of the module asks four things of whatever is playing: play, pause,
// where are we, and are we paused. A <video> element answers all four
// instantly. YouTube and Vimeo answer them across a postMessage boundary, so
// their position is polled or pushed and their paused state arrives as an
// event.
//
// So all of them are wrapped to look like the element, and the difference is
// confined to this file. The wrapper also publishes itself as window.KAIVIDEO,
// which is what lets the proctoring monitor watch a YouTube or Vimeo lesson
// without knowing anything about either.
//
// HLS is the odd one out and the cheapest: it plays in a real <video>, with the
// stream attached by video.js — which Moodle already ships, with
// @videojs/http-streaming (Apache-2.0) inside it. Nothing downstream can tell
// an HLS lesson from a plain file, which is the whole point.
define([], function() {

    /** Poll interval for YouTube's playhead. Four times a second is what a
     *  <video> element's own timeupdate manages, so the question-due check
     *  behaves the same either way. */
    var POLL_MS = 250;

    /** How long to wait for Vimeo's player before calling it a failure. */
    var VIMEO_READY_MS = 15000;

    /**
     * A plain <video>. Nothing to adapt; it already is the interface.
     *
     * @param {HTMLVideoElement} element
     */
    var FileBackend = function(element) {
        this.element = element;
        this.host = element;
    };

    FileBackend.prototype.play = function() {
        return Promise.resolve(this.element.play()).catch(function() {
            return null;
        });
    };
    FileBackend.prototype.pause = function() {
        this.element.pause();
    };
    FileBackend.prototype.currentTime = function() {
        return this.element.currentTime;
    };
    FileBackend.prototype.seek = function(seconds) {
        this.element.currentTime = seconds;
    };
    FileBackend.prototype.duration = function() {
        return this.element.duration || 0;
    };
    FileBackend.prototype.isPaused = function() {
        return this.element.paused;
    };
    FileBackend.prototype.onTick = function(callback) {
        this.element.addEventListener('timeupdate', callback);
        this.element.addEventListener('seeked', callback);
    };
    FileBackend.prototype.onEnded = function(callback) {
        this.element.addEventListener('ended', callback);
    };
    FileBackend.prototype.onPlayAttempt = function(callback) {
        this.element.addEventListener('play', callback);
    };

    /**
     * YouTube, through its own iframe API.
     *
     * Its native controls are switched off. Not for tidiness: with them on, a
     * learner can drag YouTube's seek bar and resume playing from inside the
     * iframe, and "the video will not continue past an unanswered question"
     * stops being something this module can promise. Our own controls sit
     * underneath instead.
     *
     * @param {Object} player YT.Player
     */
    var YouTubeBackend = function(player) {
        var self = this;
        this.player = player;
        this.host = player.getIframe();
        this._paused = true;
        this._time = 0;
        this._tick = [];
        this._ended = [];
        this._playAttempt = [];

        window.setInterval(function() {
            try {
                self._time = player.getCurrentTime() || 0;
            } catch (error) {
                return;
            }
            self._tick.forEach(function(callback) {
                callback();
            });
        }, POLL_MS);
    };

    YouTubeBackend.prototype.play = function() {
        this._paused = false;
        this.player.playVideo();
        return Promise.resolve();
    };
    YouTubeBackend.prototype.pause = function() {
        this._paused = true;
        this.player.pauseVideo();
    };
    YouTubeBackend.prototype.currentTime = function() {
        return this._time;
    };
    YouTubeBackend.prototype.seek = function(seconds) {
        this.player.seekTo(seconds, true);
    };
    YouTubeBackend.prototype.duration = function() {
        try {
            return this.player.getDuration() || 0;
        } catch (error) {
            return 0;
        }
    };
    YouTubeBackend.prototype.isPaused = function() {
        // Tracked locally rather than read from the player: getPlayerState is
        // available synchronously but lags the instruction, so asking it right
        // after pause() can still answer "playing".
        return this._paused;
    };
    YouTubeBackend.prototype.onTick = function(callback) {
        this._tick.push(callback);
    };
    YouTubeBackend.prototype.onEnded = function(callback) {
        this._ended.push(callback);
    };
    YouTubeBackend.prototype.onPlayAttempt = function(callback) {
        this._playAttempt.push(callback);
    };
    YouTubeBackend.prototype._state = function(state) {
        var self = this;
        if (state === 0) {
            this._paused = true;
            this._ended.forEach(function(callback) {
                callback();
            });
        } else if (state === 1) {
            this._paused = false;
            this._playAttempt.forEach(function(callback) {
                callback();
            });
        } else if (state === 2) {
            this._paused = true;
        }
        return self;
    };

    /**
     * Vimeo, through its Player SDK.
     *
     * Nearly everything it answers is a Promise, which is why the playhead is
     * cached from its own timeupdate event rather than asked for: the
     * due-question check runs on every tick and has to answer synchronously.
     *
     * Its controls are not hidden here. They can be asked to go away, but
     * whether the request is honoured depends on the account the video sits in,
     * and a guarantee that holds only on some customers' accounts is not one.
     * A transparent sheet over the iframe puts them out of reach instead — see
     * the template.
     *
     * @param {Object} player Vimeo.Player
     * @param {Element} host the iframe it created
     */
    var VimeoBackend = function(player, host) {
        var self = this;
        this.player = player;
        this.host = host;
        this._paused = true;
        this._time = 0;
        this._tick = [];
        this._ended = [];
        this._playAttempt = [];
        this._duration = 0;

        player.on('timeupdate', function(data) {
            self._time = data.seconds || 0;
            self._duration = data.duration || self._duration;
            self._tick.forEach(function(callback) {
                callback();
            });
        });
        // Seeking fires no timeupdate until playback resumes, so without this
        // a learner could drag ahead while paused and the question due at the
        // new position would not come up until they pressed play.
        player.on('seeked', function(data) {
            self._time = data.seconds || 0;
            self._tick.forEach(function(callback) {
                callback();
            });
        });
        player.on('play', function() {
            self._paused = false;
            self._playAttempt.forEach(function(callback) {
                callback();
            });
        });
        player.on('pause', function() {
            self._paused = true;
        });
        player.on('ended', function() {
            self._paused = true;
            self._ended.forEach(function(callback) {
                callback();
            });
        });
    };

    VimeoBackend.prototype.play = function() {
        this._paused = false;
        return this.player.play().catch(function() {
            return null;
        });
    };
    VimeoBackend.prototype.pause = function() {
        this._paused = true;
        this.player.pause().catch(function() {
            return null;
        });
    };
    VimeoBackend.prototype.currentTime = function() {
        return this._time;
    };
    VimeoBackend.prototype.seek = function(seconds) {
        // Set locally as well as sent: the answer comes back asynchronously,
        // and a check() running in between would still read the old position.
        this._time = seconds;
        this.player.setCurrentTime(seconds).catch(function() {
            return null;
        });
    };
    VimeoBackend.prototype.duration = function() {
        return this._duration;
    };
    VimeoBackend.prototype.isPaused = function() {
        return this._paused;
    };
    VimeoBackend.prototype.onTick = function(callback) {
        this._tick.push(callback);
    };
    VimeoBackend.prototype.onEnded = function(callback) {
        this._ended.push(callback);
    };
    VimeoBackend.prototype.onPlayAttempt = function(callback) {
        this._playAttempt.push(callback);
    };

    /**
     * Put an HLS stream onto a <video> element.
     *
     * Safari plays a playlist natively; nothing else does. video.js is asked
     * for only when it is needed, so the common case costs no download.
     *
     * @param {HTMLVideoElement} element
     * @param {String} url the .m3u8
     * @return {Promise}
     */
    /**
     * Wait until the element knows how long the video is.
     *
     * The shim announces "loaded" the moment the backend exists, and the fork
     * reads the duration then — to size the seekbar and to place every
     * interaction on it. Announced before the metadata has arrived, it reads
     * 0, builds a zero-length timeline, and no question is ever due: the
     * video stops at the first one with nothing on the screen.
     *
     * Invisible wherever the file is already in the browser's cache, which is
     * every machine the player was developed on, and certain on a learner's
     * first visit.
     *
     * An element that fails to load is let through as it always was; the
     * browser's own error is the more useful report than a promise that
     * never settles.
     *
     * @param {HTMLVideoElement} element
     * @return {Promise<HTMLVideoElement>}
     */
    var whenMetadata = function(element) {
        if (!element || element.readyState >= 1) {
            return Promise.resolve(element);
        }
        return new Promise(function(resolve) {
            var done = function() {
                element.removeEventListener('loadedmetadata', done);
                element.removeEventListener('error', done);
                resolve(element);
            };
            element.addEventListener('loadedmetadata', done);
            element.addEventListener('error', done);
        });
    };

    var attachStream = function(element, url) {
        var native = element.canPlayType('application/vnd.apple.mpegurl');
        if (native === 'probably' || native === 'maybe') {
            element.src = url;
            return Promise.resolve(element);
        }

        return new Promise(function(resolve, reject) {
            require(['media_videojs/video-lazy'], function(videojs) {
                // controls false, and the element left in place: video.js keeps
                // the <video> it was given as its playback element, so
                // [data-region="video"] still refers to the thing that plays
                // and the file backend keeps working unchanged.
                var player = videojs(element, {controls: false, fluid: false});
                player.src({src: url, type: 'application/x-mpegURL'});
                resolve(element);
            }, function() {
                reject(new Error('videojs_unavailable'));
            });
        });
    };

    /**
     * Load Vimeo's SDK once, and hand back its Player constructor.
     *
     * Through RequireJS rather than a <script> tag, which is what YouTube's
     * API gets. Vimeo ships a UMD bundle: dropped onto a page that has an AMD
     * loader it calls define() anonymously, and RequireJS rejects that with
     * "Mismatched anonymous define() module" because it never asked for it.
     * The page then had no player and an error nothing on it explained.
     *
     * Asking RequireJS to fetch it means the define() belongs to a request it
     * is tracking, which is the case the loader is built for. The alternative —
     * hiding define.amd while the script loads — mutates a global that every
     * other module on the page is using, to work around one file.
     *
     * @return {Promise<Function>} the Player constructor
     */
    var vimeoReady = null;
    var loadVimeo = function() {
        if (vimeoReady) {
            return vimeoReady;
        }
        vimeoReady = new Promise(function(resolve, reject) {
            if (window.Vimeo && window.Vimeo.Player) {
                resolve(window.Vimeo.Player);
                return;
            }
            require(['https://player.vimeo.com/api/player.js'], function(module) {
                // The AMD build exports the constructor; the global build hangs
                // it off window.Vimeo. Either can turn up depending on how the
                // bundle decided to define itself.
                var Player = (module && module.Player) || module
                    || (window.Vimeo && window.Vimeo.Player);
                if (typeof Player !== 'function') {
                    reject(new Error('vimeo_api_unusable'));
                    return;
                }
                resolve(Player);
            }, function() {
                reject(new Error('vimeo_api_unreachable'));
            });
        });
        return vimeoReady;
    };

    /** Load YouTube's API once, however many players are on the page. */
    var apiReady = null;
    var loadApi = function() {
        if (apiReady) {
            return apiReady;
        }
        apiReady = new Promise(function(resolve, reject) {
            if (window.YT && window.YT.Player) {
                resolve(window.YT);
                return;
            }
            var previous = window.onYouTubeIframeAPIReady;
            window.onYouTubeIframeAPIReady = function() {
                if (typeof previous === 'function') {
                    previous();
                }
                resolve(window.YT);
            };
            var script = document.createElement('script');
            script.src = 'https://www.youtube.com/iframe_api';
            script.onerror = function() {
                reject(new Error('youtube_api_unreachable'));
            };
            document.head.appendChild(script);
        });
        return apiReady;
    };

    return {
        /**
         * Put a stream on a plain <video>, for pages that only need to show it.
         *
         * The editor's preview uses this: it is not taking the lesson, so it
         * keeps the browser's own controls and needs none of the rest.
         *
         * @param {String} selector
         * @param {String} url the .m3u8
         * @return {Promise}
         */
        attachStream: function(selector, url) {
            var element = document.querySelector(selector);
            return element ? attachStream(element, url) : Promise.resolve(null);
        },

        /**
         * @param {Object} config from the page
         * @param {Element} root the activity's container
         * @return {Promise<Object>} the backend
         */
        create: function(config, root) {
            var published = function(backend) {
                // The proctoring monitor looks for this. Publishing it here
                // means a YouTube or Vimeo lesson is watchable without the
                // monitor knowing what either provider is.
                window.KAIVIDEO = backend;
                return backend;
            };

            if (config.provider === 'hls') {
                var element = root.querySelector('[data-region="video"]');
                return attachStream(element, config.streamurl).then(whenMetadata).then(function() {
                    // A file backend over it, deliberately: once the stream is
                    // attached there is nothing left that is HLS-specific, and
                    // a separate wrapper would be a second copy of the same
                    // four methods waiting to drift.
                    return published(new FileBackend(element));
                });
            }

            if (config.provider === 'vimeo') {
                return loadVimeo().then(function(VimeoPlayer) {
                    // The unlisted hash travels with the id as "id:hash",
                    // because without it the player refuses to load — and an
                    // unlisted video is exactly what a paid course sits behind.
                    var parts = String(config.videoid).split(':');
                    var options = {id: parts[0], controls: false,
                        responsive: true, dnt: true};
                    if (parts[1]) {
                        options.h = parts[1];
                    }

                    var player = new VimeoPlayer(
                        root.querySelector('[data-region="vimeo"]'), options);

                    // Raced against a clock, because ready() does not always
                    // settle. A video whose privacy settings do not list this
                    // site is answered with a 401 inside the iframe, where the
                    // SDK never sees it: the promise stays pending and the
                    // learner is left looking at an empty box with nothing on
                    // the page to explain it. Not hypothetical — "which domains
                    // may embed this" is the setting customers get wrong.
                    return Promise.race([
                        player.ready(),
                        new Promise(function(resolve, reject) {
                            window.setTimeout(function() {
                                reject(new Error('vimeo_api_unusable'));
                            }, VIMEO_READY_MS);
                        })
                    ]).then(function() {
                        return published(new VimeoBackend(player, player.element));
                    });
                });
            }

            if (config.provider !== 'youtube') {
                return whenMetadata(root.querySelector('[data-region="video"]'))
                    .then(function(element) {
                        return published(new FileBackend(element));
                    });
            }

            return loadApi().then(function(YT) {
                return new Promise(function(resolve) {
                    var backend;
                    var player = new YT.Player(
                        root.querySelector('[data-region="youtube"]'), {
                            videoId: config.videoid,
                            playerVars: {
                                controls: 0,
                                disablekb: 1,
                                modestbranding: 1,
                                rel: 0,
                                playsinline: 1
                            },
                            events: {
                                onReady: function() {
                                    backend = new YouTubeBackend(player);
                                    resolve(published(backend));
                                },
                                onStateChange: function(event) {
                                    if (backend) {
                                        backend._state(event.data);
                                    }
                                }
                            }
                        });
                });
            });
        }
    };
});

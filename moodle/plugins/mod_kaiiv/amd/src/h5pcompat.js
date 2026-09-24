// The layer that lets the forked player run with no H5P underneath it.
//
// amd/src/iv/* came from h5p-interactive-video (MIT — see thirdparty/README.md)
// and it talks to a runtime: H5P.jQuery, H5P.Video, H5P.EventDispatcher,
// H5P.newRunnable and a handful of smaller things. Upstream that runtime is
// loaded by H5P core into an iframe of its own.
//
// We are not in an iframe, on purpose. The proctoring monitor drives a real
// <video> element on the same page, and a monitor that has to ask across
// postMessage cannot pause on the frame a question is due. So the runtime the
// fork expects is supplied here instead, by us, backed by our own code.
//
// The rule this file follows: provide what the fork actually calls, and
// nothing else. Every member below exists because a grep of amd/src/iv found
// it being used. An H5P API that upstream has and the fork never reaches for
// is not reimplemented here, because an unused reimplementation is a thing
// that can rot without anything noticing.
//
//   grep -rhoE "H5P\.[A-Za-z_]+" amd/src/iv/
//
// Run that after taking an upstream patch. A name in its output that is not
// below is a gap, and it will surface as an undefined-is-not-a-function at the
// moment a learner opens the activity rather than at build time.
import $ from 'jquery';
import Log from 'core/log';
// Loaded by Moodle rather than bundled, and that is not a style choice.
//
// backend.js asks requirejs for media_videojs/video-lazy when a stream needs
// it, and for Vimeo's SDK when a Vimeo video needs it — both at the moment
// they are needed and not before. A bundler sees those calls and tries to
// resolve them at build time, which turns two conditional downloads into two
// unconditional ones and fails outright on the Vimeo URL.
//
// It is also plain AMD with no imports, so a copy into amd/build is a correct
// build for it. See tools/build-plain-amd.js.
import Backend from 'mod_kaiiv/backend';

/**
 * The smallest event emitter the fork is happy with.
 *
 * Upstream this is H5P.EventDispatcher, and several of the forked classes
 * inherit from it by calling it as a constructor on themselves rather than
 * by prototype chain, so it has to work that way round too.
 */
var EventDispatcher = function() {
    var listeners = {};
    var self = this;

    self.on = function(type, listener, thisArg) {
        if (!listeners[type]) {
            listeners[type] = [];
        }
        listeners[type].push({listener: listener, thisArg: thisArg || self});
        return self;
    };

    self.once = function(type, listener, thisArg) {
        var wrapper = function(event) {
            self.off(type, wrapper);
            listener.call(thisArg || self, event);
        };
        return self.on(type, wrapper);
    };

    self.off = function(type, listener) {
        if (!listeners[type]) {
            return self;
        }
        if (!listener) {
            delete listeners[type];
            return self;
        }
        listeners[type] = listeners[type].filter(function(entry) {
            return entry.listener !== listener;
        });
        return self;
    };

    self.trigger = function(type, data, extras) {
        var event = (type instanceof Event2) ? type : new Event2(type, data, extras);
        var registered = listeners[event.type] || [];

        // Copied before iterating: handlers that remove themselves are
        // ordinary here — the fork's endscreen does it — and splicing the
        // array being walked skips the next handler.
        registered.slice().forEach(function(entry) {
            try {
                entry.listener.call(entry.thisArg, event);
            } catch (error) {
                // One broken listener must not take the rest of the
                // player down with it. A question that fails to draw is a
                // support call; a video that stops responding is an exam
                // that has to be re-sat.
                Log.error('kaiiv: listener for ' + event.type + ' threw', error);
            }
        });
        return self;
    };

    return self;
};

/**
 * H5P.Event. Named Event2 here only to keep away from the DOM's Event.
 *
 * @param {string} type
 * @param {*} data
 * @param {Object} extras
 */
var Event2 = function(type, data, extras) {
    this.type = type;
    this.data = data;
    this.extras = extras || {};
    this.scheduledForExternal = false;
};

/**
 * The page's player element, held between the stage being emptied and the
 * video being attached.
 *
 * Module-level rather than passed through, because the two ends are the fork's
 * to schedule: player.js hands it over before constructing the player, and the
 * fork calls video.attach() somewhere inside its own setup. There is no
 * argument that travels between those two points.
 */
var reservedElement = null;

/**
 * @param {Element} element already removed from the document
 */
var reservePlayerElement = function(element) {
    reservedElement = element;
};

/**
 * @return {Element|null} the reserved element, once
 */
var takeReservedElement = function() {
    var element = reservedElement;
    reservedElement = null;
    return element;
};

/**
 * H5P.Video, over our own backends.
 *
 * The fork asks a video for rather more than mod_kaivideo's player does —
 * qualities, captions, playback rate — and our backends answer none of
 * those. They return empty lists rather than throwing, and the fork's own
 * code already hides a control whose list is empty, so an unsupported
 * feature disappears from the UI instead of appearing and failing.
 *
 * @param {Object} params what to play, in our source::url() shape
 * @param {number} contentId unused; kept because the fork passes it
 * @param {Object} extras unused; kept because the fork passes it
 */
var Video = function(params, contentId, extras) {
    EventDispatcher.call(this);
    var self = this;

    self.params = params;
    self.contentId = contentId;
    self.extras = extras;

    /** The resolved backend, once attach() has built one. */
    var backend = null;
    /** Queued calls made before the backend existed. Pausing a video that
     *  has not finished loading is normal — the fork does it when an
     *  interaction is due at second zero — and dropping those calls makes
     *  the first question of an activity the one that does not work. */
    var pending = [];

    var whenReady = function(fn) {
        if (backend) {
            fn(backend);
        } else {
            pending.push(fn);
        }
    };

    self.attach = function($wrapper) {
        var root = $wrapper.get(0);

        // Put the page's own player element into the wrapper the fork built.
        //
        // The fork empties the stage before it builds its own DOM, which
        // destroys the <video> that templates/player.mustache put there. So
        // player.js takes it out of the document first and leaves it here,
        // and this is where it goes back in.
        //
        // Moved rather than recreated, and that is the point: the proctoring
        // adapter looks for a real <video> on the page, and re-creating one
        // would leave anything already holding a reference watching a
        // detached node with no way to find out.
        var reserved = takeReservedElement();
        if (reserved && !root.contains(reserved)) {
            root.appendChild(reserved);
        }

        return Backend.create(self.params, root).then(function(built) {
            backend = built;

            backend.onTick(function() {
                self.trigger('stateUpdate');
            });
            backend.onEnded(function() {
                self.trigger('stateChange', Video.ENDED);
            });
            backend.onPlayAttempt(function(playing) {
                self.trigger('stateChange',
                    playing ? Video.PLAYING : Video.PAUSED);
            });

            pending.forEach(function(fn) {
                fn(backend);
            });
            pending = [];

            self.trigger('ready');
            self.trigger('loaded');
            return backend;
        }).catch(function(error) {
            Log.error('kaiiv: video backend failed to start', error);
            self.trigger('error', error);
            throw error;
        });
    };

    self.play = function() {
        whenReady(function(b) {
            b.play();
        });
    };
    self.pause = function() {
        whenReady(function(b) {
            b.pause();
        });
    };
    self.seek = function(seconds) {
        whenReady(function(b) {
            b.seek(seconds);
        });
    };
    self.getCurrentTime = function() {
        return backend ? backend.currentTime() : 0;
    };
    self.getDuration = function() {
        return backend ? backend.duration() : 0;
    };
    self.isPaused = function() {
        return backend ? backend.isPaused() : true;
    };
    self.isLoaded = function() {
        return backend !== null;
    };

    /**
     * Which of upstream's video handlers we are standing in for.
     *
     * These three strings are not ours to choose. The fork compares against
     * them by name in half a dozen places — `!== 'Html5'` decides whether the
     * poster gets a click-to-play layer, `=== 'YouTube'` decides how the
     * quality menu is built, `=== 'VimeoPlayer'` decides whether a play
     * button is drawn over the frame. Returning "file" or "kaiiv" here would
     * be answering a question nobody asked, and every one of those branches
     * would silently take the wrong side.
     *
     * @return {String}
     */
    self.getHandlerName = function() {
        var provider = (self.params && self.params.provider) || 'file';
        if (provider === 'youtube') {
            return 'YouTube';
        }
        if (provider === 'vimeo') {
            return 'VimeoPlayer';
        }
        // A file and an HLS stream are both a real <video>, which is the
        // whole reason HLS was cheap to add.
        return 'Html5';
    };

    // A property, not a method, and its *absence* is meaningful.
    //
    // The fork reads `video.pressToPlay !== undefined` to tell a YouTube
    // player from a native one, and `!video.pressToPlay` to decide whether it
    // may start playback itself. Upstream only the YouTube handler defines
    // it, so defining it here for everything would make every video look like
    // a YouTube one to six branches that care.
    //
    // It means "this player will not start without a real user gesture".
    // YouTube's iframe API enforces that; a <video> on the same page does
    // not, and Vimeo is driven through its own play button, which the fork
    // handles by handler name instead.
    if ((params && params.provider) === 'youtube') {
        self.pressToPlay = true;
    }

    /**
     * How much is buffered, as a fraction.
     *
     * Drawn as the lighter bar behind the seekbar. Only a real <video> can
     * answer it; the two iframe providers do not expose it, and -1 is
     * upstream's own "do not know", which the fork already handles by leaving
     * the bar alone rather than drawing it empty.
     *
     * @return {Number}
     */
    self.getBuffered = function() {
        var host = backend && backend.host;
        if (!host || !host.buffered || !host.buffered.length || !host.duration) {
            return -1;
        }
        return host.buffered.end(host.buffered.length - 1) / host.duration * 100;
    };

    /**
     * Put the video back to the beginning for another go.
     *
     * The fork calls this when a learner restarts. Seeking rather than
     * reloading: the element is the one the proctoring adapter holds a
     * reference to, and replacing it would leave the monitor watching a
     * detached node with no way to find out.
     */
    self.resetTask = function() {
        whenReady(function(b) {
            b.pause();
            b.seek(0);
        });
    };

    // Declared unsupported rather than left undefined. The fork calls
    // these unconditionally while building its controls and reads the
    // answer to decide what to show.
    self.getQualities = function() {
        return [];
    };
    self.setQuality = function() {};
    self.getQuality = function() {
        return null;
    };
    self.getCaptionsTracks = function() {
        return [];
    };
    self.setCaptionsTrack = function() {};
    self.getCaptionsTrack = function() {
        return null;
    };
    self.getPlaybackRates = function() {
        return [];
    };
    self.setPlaybackRate = function() {};
    self.getPlaybackRate = function() {
        return 1;
    };

    self.mute = function() {
        whenReady(function(b) {
            if (b.host && 'muted' in b.host) {
                b.host.muted = true;
            }
        });
    };
    self.unMute = function() {
        whenReady(function(b) {
            if (b.host && 'muted' in b.host) {
                b.host.muted = false;
            }
        });
    };
    self.isMuted = function() {
        return !!(backend && backend.host && backend.host.muted);
    };
    self.getVolume = function() {
        return (backend && backend.host && 'volume' in backend.host)
            ? backend.host.volume * 100 : 100;
    };
    self.setVolume = function(level) {
        whenReady(function(b) {
            if (b.host && 'volume' in b.host) {
                b.host.volume = level / 100;
            }
        });
    };

    self.resize = function() {};

    return self;
};

// The state numbers the fork compares against. These are upstream's
// values, not ours to choose: amd/src/iv/interactive-video.js compares
// against H5P.Video.PLAYING and friends in a dozen places.
Video.ENDED = 0;
Video.PLAYING = 1;
Video.PAUSED = 2;
Video.BUFFERING = 3;
Video.VIDEO_CUED = 5;

/**
 * The dialog an interaction is shown in.
 *
 * Upstream this belongs to H5P.DragNBar, which is an authoring toolbar that
 * happens to own a dialog, and which brings jQuery UI and a drag-and-resize
 * library with it. The player needs none of that — it needs a panel over the
 * video that opens, closes and says when it did — so this is ours.
 *
 * The method list is not a design. It is what a grep of the forked code
 * asks for:
 *
 *     grep -rhoE "dnb\.dialog\.[A-Za-z_]+" amd/src/iv/
 *
 * Several do nothing, and they are written out one by one rather than
 * generated, because a no-op somebody can read is a no-op somebody can
 * correct when it turns out to have mattered.
 *
 * @param {jQuery} $container what to open inside
 */
var Dialog = function($container) {
    EventDispatcher.call(this);
    var self = this;

    // The overlay carries upstream's class as well as ours, and the panel sits
    // inside it rather than beside it. Both are the fork's expectations, not
    // a preference: it finds the dialog by '.h5p-dialog-wrapper', and when a
    // dialog opens it makes everything on the player untabbable except what
    // is inside that element. With no such element $.contains() was handed
    // undefined and threw, and with the panel outside it the dialog's own
    // buttons would be the ones taken out of the tab order.
    var $overlay = $('<div>', {
        'class': 'h5p-dialog-wrapper kaiiv-dialog-overlay',
        'hidden': true,
    });
    var $dialog = $('<div>', {
        'class': 'kaiiv-dialog',
        'role': 'dialog',
        'aria-modal': 'true',
        'hidden': true,
    });
    var $inner = $('<div>', {'class': 'kaiiv-dialog-inner'}).appendTo($dialog);
    var $close = $('<button>', {
        'type': 'button',
        'class': 'kaiiv-dialog-close',
        'aria-label': 'Close',
        'html': '&times;',
    }).appendTo($dialog);

    $overlay.append($dialog);
    $container.append($overlay);

    $close.on('click', function() {
        self.close();
    });

    /** What had focus before the dialog took it. */
    var returnFocusTo = null;

    self.$inner = $inner;
    self.$dialog = $dialog;
    // The wrapper — overlay and frame together — which the toolbar hands out
    // as $dialogContainer.
    self.$wrapper = $overlay;

    /**
     * @param {jQuery} $content
     */
    self.open = function($content) {
        returnFocusTo = document.activeElement;

        if ($content) {
            $inner.empty().append($content);
        }
        $overlay.prop('hidden', false);
        $dialog.prop('hidden', false);

        // Focus moves into the dialog, not merely onto it. A modal that opens
        // behind the keyboard is a modal a learner using one cannot answer,
        // and the interaction inside is the entire activity.
        var focusable = $dialog.find(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        ).filter(':visible');
        (focusable.length ? focusable.first() : $dialog).trigger('focus');

        self.trigger('open');
    };

    self.close = function() {
        $dialog.prop('hidden', true);
        $overlay.prop('hidden', true);

        // Focus goes back where it came from. Left in a hidden dialog it goes
        // to the document body, and the next Tab starts from the top of the
        // page rather than from the video.
        if (returnFocusTo && returnFocusTo.focus) {
            returnFocusTo.focus();
        }
        returnFocusTo = null;

        self.trigger('close');
    };

    self.openOverlay = function() {
        $overlay.prop('hidden', false);
    };
    self.closeOverlay = function() {
        // The overlay is also the dialog's frame now, so it only goes when
        // the dialog is not using it.
        if ($dialog.prop('hidden')) {
            $overlay.prop('hidden', true);
        }
    };
    self.disableOverlay = function() {
        $overlay.addClass('kaiiv-dialog-overlay-disabled');
    };

    self.addLibraryClass = function(name) {
        $dialog.addClass('kaiiv-dialog-' + String(name).replace(/[^\w-]/g, '-'));
    };
    self.toggleClass = function(name, on) {
        $dialog.toggleClass(name, !!on);
    };
    self.hideCloseButton = function() {
        // Used for an interaction the learner must deal with rather than
        // dismiss — which is most of ours. The button is hidden rather than
        // removed so that close() still works for the code paths that close
        // the dialog after an answer.
        $close.prop('hidden', true);
    };

    self.getDialogWidth = function() {
        return $dialog.width() || 0;
    };
    self.getMaxSize = function() {
        return {
            width: $container.width() || 0,
            height: $container.height() || 0,
        };
    };

    // Upstream positions and sizes the dialog against the drag-and-drop
    // canvas it lives on. Ours is a centred panel laid out by CSS, so there
    // is nothing to compute — and computing something anyway would be a
    // second layout fighting the first.
    self.position = function() {};
    self.removeStaticWidth = function() {};
    self.scroll = function() {};

    return self;
};

/**
 * The toolbar, reduced to the part the player uses.
 *
 * @param {Array} buttons ignored; upstream's authoring buttons
 * @param {jQuery} $element the video wrapper
 * @param {jQuery} $container
 */
var DragNBar = function(buttons, $element, $container) {
    var self = this;

    self.dialog = new Dialog($container || $element);

    // Read by the fork when a dialog closes: it waits for the container's
    // transitionend to reset an image's size. Ours has no transition, so the
    // handler it attaches never runs — which is the right outcome, since the
    // sizes it would be undoing were never set — but the container has to be
    // there to attach to. Its absence threw inside the close handler, which
    // left the fork halfway through closing the image and unable to open the
    // link that came after it.
    self.$dialogContainer = self.dialog.$wrapper;

    // Read by the fork rather than called. Declared with their upstream
    // starting values so that the branches testing them take the same side
    // they would there.
    self.focusedElement = undefined;
    self.newElement = undefined;
    self.calledFromResetTask = false;

    // Authoring. Present because the player calls them on paths shared with
    // the editor, and doing nothing is the correct behaviour when there is no
    // editor to tell.
    self.add = function() {};
    self.blurAll = function() {};

    return self;
};

/**
 * Content types the fork names but that we do not carry.
 *
 * interaction.js checks the library name of an interaction to decide how
 * to frame it — whether it gets a title bar, whether it can be a poster.
 * Those checks are identity comparisons against constructors, so the names
 * have to exist. What they must not do is silently draw nothing when
 * something reaches them, because an interaction that renders as an empty
 * box is a support call that starts with "the question is blank".
 *
 * Our interactions are built by interactions.js and never go through
 * newRunnable, so reaching one of these means content from somewhere else
 * — an imported H5P package, most likely — and saying so is more useful
 * than failing quietly.
 *
 * @param {string} name
 * @return {Function}
 */
var unsupported = function(name) {
    var Type = function() {
        EventDispatcher.call(this);
        this.attach = function($wrapper) {
            Log.warn('kaiiv: content type ' + name + ' is not carried by this fork');
            $wrapper.append($('<div>', {
                'class': 'kaiiv-unsupported',
                'text': name
            }));
        };
        return this;
    };
    Type.machineName = name;
    return Type;
};

var H5P = {
    jQuery: $,
    EventDispatcher: EventDispatcher,
    Video: Video,

    // Not an H5P API. Ours, and the only way the page's own <video> survives
    // the fork emptying the stage it was sitting in. player.js calls it before
    // constructing the player; Video.attach puts the element back.
    reservePlayerElement: reservePlayerElement,

    // The fork registers itself under these two and then reads them back
    // — interaction.js reaches for H5P.InteractiveVideo to find the
    // player it belongs to, and the player reaches for
    // H5P.InteractiveVideoInteraction to build one.
    //
    // Upstream that happens in src/entries/dist.js, which assigns them to
    // the global H5P after the modules load. Here player.js assigns them
    // to this object at boot, before constructing anything.
    //
    // Declared as null rather than left off so that check_fork.py sees
    // them. They are the one kind of name that is legitimately missing at
    // this point, and a checker that cannot tell "filled in later" from
    // "forgotten" is a checker somebody switches off.
    InteractiveVideo: null,
    InteractiveVideoInteraction: null,

    /**
     * Upstream builds a child content type from a library name. Ours are
     * built by interactions.js, which is wired in by player.js; this stays
     * as the path for anything the fork constructs on its own.
     */
    newRunnable: function(library) {
        var name = (library && library.library) ? library.library.split(' ')[0] : 'unknown';
        var Type = H5P[name.replace('H5P.', '')] || unsupported(name);
        return new Type(library && library.params);
    },

    /** Upstream resolves a file inside an H5P package. Ours are already
     *  URLs, issued by pluginfile.php with enrolment checked. */
    getPath: function(path) {
        return path;
    },

    isEmpty: function(value) {
        return value === undefined || value === null || value === ''
            || (Array.isArray(value) && value.length === 0);
    },

    error: function() {
        Log.error.apply(Log, arguments);
    },

    createTitle: function(raw, maxLength) {
        if (!raw) {
            return '';
        }
        var text = $('<div>').html(raw).text();
        var limit = maxLength || 60;
        return text.length > limit ? text.substr(0, limit - 1) + '…' : text;
    },

    on: function(instance, type, listener) {
        instance.on(type, listener);
    },
    trigger: function(instance, type, data) {
        instance.trigger(type, data);
    },

    // --- fullscreen ---------------------------------------------------
    // Upstream has its own semi-fullscreen for iframes that cannot go
    // native. We are not in an iframe, so this is the browser's own.
    fullScreenBrowserPrefix: (document.fullscreenEnabled ? '' : undefined),
    fullscreenSupported: !!document.fullscreenEnabled,
    isFullscreen: false,
    fullScreen: function(element) {
        var node = element && element.get ? element.get(0) : element;
        if (node && node.requestFullscreen) {
            node.requestFullscreen();
            H5P.isFullscreen = true;
        }
    },
    exitFullScreen: function() {
        if (document.exitFullscreen && document.fullscreenElement) {
            document.exitFullscreen();
        }
        H5P.isFullscreen = false;
    },

    // --- copyright ------------------------------------------------------
    // Upstream collects attribution out of the H5P package and shows it in
    // a dialog. Our videos come from a Moodle file area or a URL an author
    // typed, and neither carries that metadata, so there is nothing to
    // collect. The names exist because the fork constructs them; the
    // button that would open the dialog is switched off in player.js.
    ContentCopyrights: unsupported('ContentCopyrights'),
    MediaCopyright: unsupported('MediaCopyright'),
    Thumbnail: unsupported('Thumbnail'),
    getCopyrights: function() {
        return undefined;
    },

    // The dialog an interaction opens in, and the toolbar it hangs off.
    //
    // It would be easy to read the name as editor-only — that is what it is
    // for upstream, and it is what this entry said until the smoke test
    // found otherwise. The player constructs one with `disableEditor: true`
    // purely to get at `.dialog`, which is how every button interaction is
    // shown at runtime.
    DragNBar: DragNBar,
    // Genuinely editor-only: the handle drawn around a selected element while
    // authoring. Our editor is our own and never constructs one.
    DragNBarElement: unsupported('DragNBarElement'),

    // --- content types we do not carry -----------------------------------
    Text: unsupported('H5P.Text'),
    Image: unsupported('H5P.Image'),
    Link: unsupported('H5P.Link'),
    Table: unsupported('H5P.Table'),
    Nil: unsupported('H5P.Nil'),
    Summary: unsupported('H5P.Summary'),
    FreeTextQuestion: unsupported('H5P.FreeTextQuestion'),
    GoToQuestion: unsupported('H5P.GoToQuestion'),
    Questionnaire: unsupported('H5P.Questionnaire'),
    IVHotspot: unsupported('H5P.IVHotspot'),
    Components: unsupported('H5P.Components'),

    /**
     * xAPI, stubbed.
     *
     * Upstream reports results over xAPI, which is how H5P tells a host
     * what a learner scored. Here the server already knows — it did the
     * marking — so an xAPI statement carrying a score from the browser is
     * at best duplicate and at worst a second, forgeable source of truth
     * for the same number.
     */
    XAPIEvent: function() {
        this.setScoredResult = function() {};
        this.getVerifiedStatementValue = function() {
            return null;
        };
        this.data = {statement: {}};
        return this;
    }
};

// Published on window as well as exported.
//
// The forked modules read a bare `H5P` at the top of their own module bodies
// — `const $ = H5P.jQuery;` is the first statement in interactive-video.js —
// which is evaluated when the module is imported, not when anything is called.
// So this assignment has to have happened before those imports are evaluated,
// and the only thing that guarantees that is import order in player.js.
//
// That is a fragile-looking arrangement and it is the least fragile one
// available: the alternative is editing every top-level statement in 8,500
// lines of forked code, which is exactly the diff we want to keep readable
// against upstream.
window.H5P = H5P;

export default H5P;

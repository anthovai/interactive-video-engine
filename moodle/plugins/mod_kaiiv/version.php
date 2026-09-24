<?php
// Interactive video, forked rather than written from nothing.
//
// mod_kaivideo next door is ours line by line, and stays. This one starts from
// H5P's Interactive Video (MIT) because the part we would otherwise spend
// months rebuilding — the timeline shell, the seekbar with interaction
// markers, bookmarks, the endscreen, the screen-reader layer — already exists
// and is permissively licensed. See thirdparty/README.md for what we took,
// what it costs us, and how to take upstream fixes later.
//
// Two things about the original we deliberately did not keep: it runs in an
// iframe, and it grades in the browser with the answers shipped to the client.
// Neither survives contact with a proctored exam. Both are replaced here, and
// that replacement is the reason this is a fork and not an installation.

defined('MOODLE_INTERNAL') || die();

$plugin->component = 'mod_kaiiv';
$plugin->version   = 2026092401;
$plugin->requires  = 2024100700; // Moodle 4.5 LTS.
// No dependencies, deliberately. This activity is installed on customers' own
// Moodle sites, most of which will not carry the proctoring stack, and it used
// to refuse to install without local_kaiproctor. It needs only the engine,
// which it is pointed at from its own settings page. When local_kaiproctor is
// present its engine address and key are read as well, and it can monitor
// these activities like any other video — but neither is required.
$plugin->maturity  = MATURITY_BETA;
$plugin->release   = '0.2.1';

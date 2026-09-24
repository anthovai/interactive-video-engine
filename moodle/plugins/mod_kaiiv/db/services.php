<?php
// What the player may ask the server to do.
//
// Two things, and nothing else. The player cannot ask for a timeline — it is
// handed one when the page is built — and it certainly cannot ask what the
// answer to something is. Every function here is ajax => true because the only
// caller is the page itself; none is in a service, so none is reachable with a
// token by anything outside.

defined('MOODLE_INTERNAL') || die();

$functions = [
    'mod_kaiiv_answer' => [
        'classname' => 'mod_kaiiv\external\answer',
        'description' => 'Submit an answer to one interaction and be told how it did.',
        'type' => 'write',
        'ajax' => true,
        'capabilities' => 'mod/kaiiv:answer',
    ],
    'mod_kaiiv_record_progress' => [
        'classname' => 'mod_kaiiv\external\record_progress',
        'description' => 'Record how far through the video the learner has got.',
        'type' => 'write',
        'ajax' => true,
        'capabilities' => 'mod/kaiiv:view',
    ],
];

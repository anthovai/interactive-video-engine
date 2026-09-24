<?php
// Who may do what. Same shape as mod_kaivideo, for the same reasons: editing
// the timeline means seeing correct answers, so it is not the view capability.

defined('MOODLE_INTERNAL') || die();

$capabilities = [
    'mod/kaiiv:addinstance' => [
        'riskbitmask' => RISK_XSS,
        'captype' => 'write',
        'contextlevel' => CONTEXT_COURSE,
        'archetypes' => ['editingteacher' => CAP_ALLOW, 'manager' => CAP_ALLOW],
        'clonepermissionsfrom' => 'moodle/course:manageactivities',
    ],
    'mod/kaiiv:view' => [
        'captype' => 'read',
        'contextlevel' => CONTEXT_MODULE,
        'archetypes' => ['student' => CAP_ALLOW, 'teacher' => CAP_ALLOW,
            'editingteacher' => CAP_ALLOW, 'manager' => CAP_ALLOW],
    ],
    'mod/kaiiv:answer' => [
        'captype' => 'write',
        'contextlevel' => CONTEXT_MODULE,
        'archetypes' => ['student' => CAP_ALLOW],
    ],
    'mod/kaiiv:editinteractions' => [
        'riskbitmask' => RISK_XSS,
        'captype' => 'write',
        'contextlevel' => CONTEXT_MODULE,
        'archetypes' => ['editingteacher' => CAP_ALLOW, 'manager' => CAP_ALLOW],
    ],
    'mod/kaiiv:viewreport' => [
        'captype' => 'read',
        'contextlevel' => CONTEXT_MODULE,
        'archetypes' => ['teacher' => CAP_ALLOW, 'editingteacher' => CAP_ALLOW,
            'manager' => CAP_ALLOW],
    ],
];

<?php
// Where the interactive video engine is, and how to prove we are allowed to use it.
//
// Both empty by default, and empty means "use the proctoring plugin's settings
// if it is installed, otherwise the address our own stack gives the engine".
// A site that runs our full stack therefore never visits this page. A
// customer's own Moodle, with only this activity added, sets both here.

defined('MOODLE_INTERNAL') || die();

if ($ADMIN->fulltree) {
    $settings->add(new admin_setting_configtext(
        'mod_kaiiv/engineurl',
        get_string('settings:engineurl', 'mod_kaiiv'),
        get_string('settings:engineurl_desc', 'mod_kaiiv'),
        '',
        PARAM_URL
    ));

    $settings->add(new admin_setting_configpasswordunmask(
        'mod_kaiiv/apikey',
        get_string('settings:apikey', 'mod_kaiiv'),
        get_string('settings:apikey_desc', 'mod_kaiiv'),
        ''
    ));
}

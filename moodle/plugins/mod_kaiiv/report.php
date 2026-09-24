<?php
// How the class did.

require_once(__DIR__ . '/../../config.php');

$cmid = required_param('cmid', PARAM_INT);

[$course, $cm] = get_course_and_cm_from_cmid($cmid, 'kaiiv');
require_login($course, true, $cm);

$context = context_module::instance($cm->id);
require_capability('mod/kaiiv:viewreport', $context);

$activity = $DB->get_record('kaiiv', ['id' => $cm->instance], '*', MUST_EXIST);

$PAGE->set_url(new moodle_url('/mod/kaiiv/report.php', ['cmid' => $cmid]));
$PAGE->set_context($context);
$PAGE->set_title(get_string('report', 'mod_kaiiv'));
$PAGE->set_heading(format_string($activity->name));

echo $OUTPUT->header();

echo $OUTPUT->render_from_template('mod_kaiiv/report',
    \mod_kaiiv\report::build((int) $activity->id, $context) + [
        'viewurl' => (new moodle_url('/mod/kaiiv/view.php',
            ['id' => $cmid]))->out(false),
    ]);

echo $OUTPUT->footer();

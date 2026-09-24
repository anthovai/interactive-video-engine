<?php
// Every interactive video in one course.
//
// Reached from the activities block, and from the link the backup's
// encode_content_links rewrites. A module that publishes those links without
// this file answers them with a 404.

require_once(__DIR__ . '/../../config.php');

$id = required_param('id', PARAM_INT);

$course = $DB->get_record('course', ['id' => $id], '*', MUST_EXIST);
require_login($course);

$context = context_course::instance($course->id);

$PAGE->set_url(new moodle_url('/mod/kaiiv/index.php', ['id' => $id]));
$PAGE->set_context($context);
$PAGE->set_title(format_string($course->fullname));
$PAGE->set_heading(format_string($course->fullname));

echo $OUTPUT->header();
echo $OUTPUT->heading(get_string('modulenameplural', 'mod_kaiiv'));

$activities = get_all_instances_in_course('kaiiv', $course);

if (!$activities) {
    notice(get_string('noinstances', 'mod_kaiiv'),
        new moodle_url('/course/view.php', ['id' => $course->id]));
} else {
    $table = new html_table();
    $table->head = [get_string('name'), get_string('moduleintro')];

    foreach ($activities as $activity) {
        // Hidden activities are listed only for whoever can see them anyway,
        // and greyed rather than dropped so a teacher can tell the difference
        // between "hidden" and "not there".
        if (!$activity->visible && !has_capability('moodle/course:viewhiddenactivities', $context)) {
            continue;
        }

        $link = html_writer::link(
            new moodle_url('/mod/kaiiv/view.php', ['id' => $activity->coursemodule]),
            format_string($activity->name),
            $activity->visible ? [] : ['class' => 'dimmed']);

        $table->data[] = [$link, format_module_intro('kaiiv', $activity,
            $activity->coursemodule)];
    }

    echo html_writer::table($table);
}

echo $OUTPUT->footer();

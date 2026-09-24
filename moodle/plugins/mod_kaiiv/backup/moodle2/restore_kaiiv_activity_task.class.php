<?php
// The restore task for one interactive video.

defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/mod/kaiiv/backup/moodle2/restore_kaiiv_stepslib.php');

class restore_kaiiv_activity_task extends restore_activity_task {

    protected function define_my_settings() {
    }

    protected function define_my_steps() {
        $this->add_step(new restore_kaiiv_activity_structure_step(
            'kaiiv_structure', 'kaiiv.xml'));
    }

    public static function define_decode_contents() {
        return [new restore_decode_content('kaiiv', ['intro'], 'kaiiv')];
    }

    public static function define_decode_rules() {
        return [
            new restore_decode_rule('KAIIVVIEWBYID',
                '/mod/kaiiv/view.php?id=$1', 'course_module'),
            new restore_decode_rule('KAIIVINDEX',
                '/mod/kaiiv/index.php?id=$1', 'course'),
        ];
    }

    public static function define_restore_log_rules() {
        return [];
    }
}

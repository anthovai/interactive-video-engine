<?php
// Putting one back.

defined('MOODLE_INTERNAL') || die();

class restore_kaiiv_activity_structure_step extends restore_activity_structure_step {

    protected function define_structure() {
        $paths = [];
        $userinfo = $this->get_setting_value('userinfo');

        $paths[] = new restore_path_element('kaiiv', '/activity/kaiiv');
        $paths[] = new restore_path_element('kaiiv_interaction',
            '/activity/kaiiv/interactions/interaction');
        $paths[] = new restore_path_element('kaiiv_bookmark',
            '/activity/kaiiv/bookmarks/bookmark');

        if ($userinfo) {
            $paths[] = new restore_path_element('kaiiv_response',
                '/activity/kaiiv/interactions/interaction/responses/response');
            $paths[] = new restore_path_element('kaiiv_progress',
                '/activity/kaiiv/progresses/progress');
        }

        return $this->prepare_activity_structure($paths);
    }

    protected function process_kaiiv($data) {
        global $DB;

        $data = (object) $data;
        $data->course = $this->get_courseid();
        $data->timecreated = $this->apply_date_offset($data->timecreated);
        $data->timemodified = $this->apply_date_offset($data->timemodified);

        $newid = $DB->insert_record('kaiiv', $data);
        $this->apply_activity_instance($newid);
    }

    protected function process_kaiiv_interaction($data) {
        global $DB;

        $data = (object) $data;
        $oldid = $data->id;
        $data->kaiivid = $this->get_new_parentid('kaiiv');
        $data->timecreated = $this->apply_date_offset($data->timecreated);

        $newid = $DB->insert_record('kaiiv_interaction', $data);
        // Responses are restored against this mapping; without it they would
        // attach to whatever interaction happened to hold the old id.
        $this->set_mapping('kaiiv_interaction', $oldid, $newid);
    }

    protected function process_kaiiv_bookmark($data) {
        global $DB;

        $data = (object) $data;
        $data->kaiivid = $this->get_new_parentid('kaiiv');

        $DB->insert_record('kaiiv_bookmark', $data);
    }

    protected function process_kaiiv_response($data) {
        global $DB;

        $data = (object) $data;
        $data->interactionid = $this->get_new_parentid('kaiiv_interaction');
        $data->userid = $this->get_mappingid('user', $data->userid);
        $data->timecreated = $this->apply_date_offset($data->timecreated);

        $DB->insert_record('kaiiv_response', $data);
    }

    protected function process_kaiiv_progress($data) {
        global $DB;

        $data = (object) $data;
        $data->kaiivid = $this->get_new_parentid('kaiiv');
        $data->userid = $this->get_mappingid('user', $data->userid);
        $data->timemodified = $this->apply_date_offset($data->timemodified);

        $DB->insert_record('kaiiv_progress', $data);
    }

    protected function after_execute() {
        $this->add_related_files('mod_kaiiv', 'intro', null);
        $this->add_related_files('mod_kaiiv', 'video', null);
    }
}

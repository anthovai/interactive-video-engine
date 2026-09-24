<?php
// The backup task for one interactive video.

defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/mod/kaiiv/backup/moodle2/backup_kaiiv_stepslib.php');

class backup_kaiiv_activity_task extends backup_activity_task {

    protected function define_my_settings() {
    }

    protected function define_my_steps() {
        $this->add_step(new backup_kaiiv_activity_structure_step(
            'kaiiv_structure', 'kaiiv.xml'));
    }

    /**
     * Rewrite links to this activity so a restored copy points at itself.
     *
     * @param string $content
     * @return string
     */
    public static function encode_content_links($content) {
        global $CFG;

        $base = preg_quote($CFG->wwwroot, '/');

        $content = preg_replace(
            '/(' . $base . '\/mod\/kaiiv\/index.php\?id\=)([0-9]+)/',
            '$@KAIIVINDEX*$2@$', $content);
        $content = preg_replace(
            '/(' . $base . '\/mod\/kaiiv\/view.php\?id\=)([0-9]+)/',
            '$@KAIIVVIEWBYID*$2@$', $content);

        return $content;
    }
}

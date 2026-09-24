<?php
// What goes into a course backup.
//
// Declaring FEATURE_BACKUP_MOODLE2 without writing this does not degrade
// gracefully: backing up any course containing the activity dies with "class
// not found", and the failure is attributed to the backup rather than to us.
// mod_kaivideo shipped exactly that once, and it was found by running a
// backup rather than by reading anything.
//
// The correct answers travel with the questions, in the answers column, and
// that is right: a backup is the teacher's content leaving one site for
// another, not a payload sent to a browser. The rule this plugin enforces is
// about what reaches a learner, and a .mbz file does not.

defined('MOODLE_INTERNAL') || die();

class backup_kaiiv_activity_structure_step extends backup_activity_structure_step {

    protected function define_structure() {
        $userinfo = $this->get_setting_value('userinfo');

        $kaiiv = new backup_nested_element('kaiiv', ['id'], [
            'name', 'intro', 'introformat', 'videourl', 'posterstart',
            'showbookmarks', 'showendscreen', 'mustanswer', 'allowreview',
            'maxattempts', 'grade', 'completionanswerall', 'completionwatched',
            'timecreated', 'timemodified',
        ]);

        $interactions = new backup_nested_element('interactions');
        $interaction = new backup_nested_element('interaction', ['id'], [
            'starttime', 'endtime', 'type', 'displaytype', 'pausevideo',
            'x', 'y', 'width', 'height', 'label', 'category',
            'content', 'answers', 'feedback', 'sortorder', 'timecreated',
        ]);

        $bookmarks = new backup_nested_element('bookmarks');
        $bookmark = new backup_nested_element('bookmark', ['id'], [
            'attime', 'label',
        ]);

        $responses = new backup_nested_element('responses');
        $response = new backup_nested_element('response', ['id'], [
            'userid', 'response', 'category', 'attempt', 'correct', 'timecreated',
        ]);

        $progresses = new backup_nested_element('progresses');
        $progress = new backup_nested_element('progress', ['id'], [
            'userid', 'furthest', 'finished', 'timemodified',
        ]);

        $kaiiv->add_child($interactions);
        $interactions->add_child($interaction);
        $interaction->add_child($responses);
        $responses->add_child($response);

        $kaiiv->add_child($bookmarks);
        $bookmarks->add_child($bookmark);

        $kaiiv->add_child($progresses);
        $progresses->add_child($progress);

        $kaiiv->set_source_table('kaiiv', ['id' => backup::VAR_ACTIVITYID]);
        $interaction->set_source_table('kaiiv_interaction',
            ['kaiivid' => backup::VAR_PARENTID], 'starttime ASC, sortorder ASC, id ASC');
        $bookmark->set_source_table('kaiiv_bookmark',
            ['kaiivid' => backup::VAR_PARENTID], 'attime ASC, id ASC');

        // Answers and watch position are somebody's record, so they travel
        // only when the backup was asked to include user data.
        if ($userinfo) {
            $response->set_source_table('kaiiv_response',
                ['interactionid' => backup::VAR_PARENTID]);
            $progress->set_source_table('kaiiv_progress',
                ['kaiivid' => backup::VAR_PARENTID]);
        }

        $response->annotate_ids('user', 'userid');
        $progress->annotate_ids('user', 'userid');

        $kaiiv->annotate_files('mod_kaiiv', 'intro', null);
        // The video itself when it was uploaded rather than linked. Without
        // this the course restores with a working timeline against nothing to
        // play, which looks like the questions broke.
        $kaiiv->annotate_files('mod_kaiiv', 'video', null);

        return $this->prepare_activity_structure($kaiiv);
    }
}

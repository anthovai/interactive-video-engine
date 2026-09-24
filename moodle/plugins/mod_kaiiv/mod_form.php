<?php
// Creating the activity. Interactions are added afterwards, against the video,
// because choosing a timestamp without seeing the frame is guesswork.

defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/course/moodleform_mod.php');

class mod_kaiiv_mod_form extends moodleform_mod {

    public function definition() {
        $mform = $this->_form;

        $mform->addElement('text', 'name', get_string('name'), ['size' => 64]);
        $mform->setType('name', PARAM_TEXT);
        $mform->addRule('name', null, 'required', null, 'client');

        $this->standard_intro_elements();

        // Upload first in the list, because it is the option most teachers can
        // actually take. Asking for a URL assumes somewhere to put the file,
        // which is a thing most people teaching a course do not have.
        $mform->addElement('select', 'sourcetype',
            get_string('sourcetype', 'mod_kaiiv'), [
                \mod_kaiiv\source::FILE => get_string('source:upload', 'mod_kaiiv'),
                'url' => get_string('source:url', 'mod_kaiiv'),
            ]);
        $mform->setDefault('sourcetype', \mod_kaiiv\source::FILE);
        $mform->addHelpButton('sourcetype', 'sourcetype', 'mod_kaiiv');

        $mform->addElement('filemanager', 'videofile',
            get_string('videofile', 'mod_kaiiv'), null, self::filemanager_options());
        $mform->addHelpButton('videofile', 'videofile', 'mod_kaiiv');
        $mform->hideIf('videofile', 'sourcetype', 'neq', \mod_kaiiv\source::FILE);

        $mform->addElement('url', 'videourl', get_string('videourl', 'mod_kaiiv'),
            ['size' => 64], ['usefilepicker' => false]);
        $mform->setType('videourl', PARAM_URL);
        $mform->addHelpButton('videourl', 'videourl', 'mod_kaiiv');
        $mform->hideIf('videourl', 'sourcetype', 'neq', 'url');

        // ---- playback -----------------------------------------------------
        $mform->addElement('header', 'playback', get_string('playback', 'mod_kaiiv'));

        $mform->addElement('advcheckbox', 'mustanswer',
            get_string('mustanswer', 'mod_kaiiv'));
        $mform->setDefault('mustanswer', 1);
        $mform->addHelpButton('mustanswer', 'mustanswer', 'mod_kaiiv');

        $mform->addElement('advcheckbox', 'posterstart',
            get_string('posterstart', 'mod_kaiiv'));
        $mform->setDefault('posterstart', 1);

        $mform->addElement('advcheckbox', 'showbookmarks',
            get_string('showbookmarks', 'mod_kaiiv'));
        $mform->setDefault('showbookmarks', 1);

        $mform->addElement('advcheckbox', 'showendscreen',
            get_string('showendscreen', 'mod_kaiiv'));
        $mform->setDefault('showendscreen', 1);
        $mform->addHelpButton('showendscreen', 'showendscreen', 'mod_kaiiv');

        // ---- answering ----------------------------------------------------
        $mform->addElement('header', 'answering', get_string('answering', 'mod_kaiiv'));

        $mform->addElement('advcheckbox', 'allowreview',
            get_string('allowreview', 'mod_kaiiv'));
        $mform->setDefault('allowreview', 1);
        $mform->addHelpButton('allowreview', 'allowreview', 'mod_kaiiv');

        // Zero first, and labelled rather than left as a bare 0. "Unlimited"
        // is the setting most activities want and the one a number field
        // expresses worst.
        $attempts = ['0' => get_string('attempts:unlimited', 'mod_kaiiv')];
        foreach ([1, 2, 3, 4, 5] as $count) {
            $attempts[(string) $count] = $count;
        }
        $mform->addElement('select', 'maxattempts',
            get_string('maxattempts', 'mod_kaiiv'), $attempts);
        $mform->setDefault('maxattempts', 0);
        $mform->addHelpButton('maxattempts', 'maxattempts', 'mod_kaiiv');
        $mform->hideIf('maxattempts', 'allowreview', 'eq', 0);

        $this->standard_grading_coursemodule_elements();
        $this->standard_coursemodule_elements();
        $this->add_action_buttons();
    }

    /**
     * What the file picker will accept.
     *
     * One file, and video types only. `maxbytes => 0` inherits whatever the
     * site and course allow rather than inventing a third limit that an admin
     * would have to find out about by hitting it.
     *
     * @return array
     */
    public static function filemanager_options(): array {
        return [
            'subdirs' => 0,
            'maxfiles' => 1,
            'maxbytes' => 0,
            'accepted_types' => ['video'],
        ];
    }

    /**
     * Fill in the file picker, and work out which option the author chose.
     *
     * The choice is derived from what is there rather than stored: a column
     * saying "this uses an upload" can end up disagreeing with whether a file
     * exists, and the activity is then broken in a way the form cannot show.
     *
     * @param array $data
     */
    public function data_preprocessing(&$data) {
        $draft = file_get_submitted_draft_itemid('videofile');
        $context = $this->context ?? null;

        file_prepare_draft_area($draft, $context ? $context->id : null,
            'mod_kaiiv', \mod_kaiiv\source::AREA, 0, self::filemanager_options());
        $data['videofile'] = $draft;

        if (!empty($data['instance'])) {
            $uploaded = $context
                && \mod_kaiiv\source::stored_file($context->id) !== null;
            $data['sourcetype'] = $uploaded ? \mod_kaiiv\source::FILE : 'url';
        }
    }

    /**
     * @param array $data
     * @param array $files
     * @return array
     */
    public function validation($data, $files) {
        $errors = parent::validation($data, $files);

        if (($data['sourcetype'] ?? '') === 'url') {
            if (empty($data['videourl'])) {
                $errors['videourl'] = get_string('required');
            } else if (!\mod_kaiiv\source::is_playable($data['videourl'])) {
                // The commonest authoring mistake is pasting a page that
                // contains a video rather than the video. Caught here, because
                // otherwise it reaches the learner as an empty player with
                // nothing to explain it.
                $errors['videourl'] = get_string('error:notplayable', 'mod_kaiiv');
            }
            return $errors;
        }

        // An activity with neither a file nor an address is a black rectangle
        // with no explanation, so it is refused at the point somebody can
        // still do something about it.
        $draft = (int) ($data['videofile'] ?? 0);
        if (!$draft || !file_get_drafarea_files($draft)->list) {
            $errors['videofile'] = get_string('error:novideo', 'mod_kaiiv');
        }

        return $errors;
    }

    /**
     * The completion rules that mean something for a video.
     *
     * @return array of element names
     */
    public function add_completion_rules() {
        $mform = $this->_form;

        $mform->addElement('checkbox', 'completionanswerall',
            get_string('completionanswerall', 'mod_kaiiv'),
            get_string('completionanswerall_label', 'mod_kaiiv'));
        $mform->addHelpButton('completionanswerall', 'completionanswerall', 'mod_kaiiv');

        $mform->addElement('checkbox', 'completionwatched',
            get_string('completionwatched', 'mod_kaiiv'),
            get_string('completionwatched_label', 'mod_kaiiv'));
        $mform->addHelpButton('completionwatched', 'completionwatched', 'mod_kaiiv');

        return ['completionanswerall', 'completionwatched'];
    }

    /**
     * @param array $data
     * @return bool
     */
    public function completion_rule_enabled($data) {
        return !empty($data['completionanswerall'])
            || !empty($data['completionwatched']);
    }
}

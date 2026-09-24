<?php
// One form for ten kinds of interaction.
//
// The alternative is ten forms, or one form that reloads when the type
// changes. Both were rejected for the same reason: an author who picks the
// wrong type, types a question into it and then corrects the type should not
// lose what they typed. Here every field exists at all times and hideIf
// decides what is on screen, so switching type back and forth costs nothing.
//
// The price is that a field belonging to another type can arrive filled in on
// submit. edit.php reads only the fields the chosen type uses, which is the
// same rule the engine applies at the other end.

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/formslib.php');

class mod_kaiiv_edit_form extends moodleform {

    /** Types that ask for a list of options. */
    const OPTION_TYPES = ['choice', 'multichoice'];

    public function definition() {
        $mform = $this->_form;
        $types = $this->_customdata['types'];

        $mform->addElement('hidden', 'cmid', $this->_customdata['cmid']);
        $mform->setType('cmid', PARAM_INT);
        $mform->addElement('hidden', 'interactionid', 0);
        $mform->setType('interactionid', PARAM_INT);

        // ---- where and what --------------------------------------------
        $mform->addElement('header', 'placement', get_string('placement', 'mod_kaiiv'));

        $mform->addElement('text', 'starttime',
            get_string('starttime', 'mod_kaiiv'), ['size' => 8]);
        $mform->setType('starttime', PARAM_FLOAT);
        $mform->addRule('starttime', null, 'required', null, 'client');
        $mform->addHelpButton('starttime', 'starttime', 'mod_kaiiv');

        // The list comes from the engine rather than from a constant here.
        // A plugin that hard-codes it drifts from the service that decides;
        // one that asks grows a type when the engine does.
        $mform->addElement('select', 'type', get_string('type', 'mod_kaiiv'), $types);
        $mform->setDefault('type', 'choice');
        $othertypes = array_values(array_diff(array_keys($types), self::OPTION_TYPES));

        $mform->addElement('text', 'label', get_string('label', 'mod_kaiiv'),
            ['size' => 40]);
        $mform->setType('label', PARAM_TEXT);
        $mform->addHelpButton('label', 'label', 'mod_kaiiv');

        $mform->addElement('text', 'category', get_string('category', 'mod_kaiiv'),
            ['size' => 30, 'list' => 'kaiiv-categories']);
        $mform->setType('category', PARAM_TEXT);
        $mform->addHelpButton('category', 'category', 'mod_kaiiv');

        // ---- the content -------------------------------------------------
        $mform->addElement('header', 'content', get_string('contentheader', 'mod_kaiiv'));
        $mform->setExpanded('content');

        $mform->addElement('editor', 'text', get_string('interactiontext', 'mod_kaiiv'),
            ['rows' => 4]);
        $mform->setType('text', PARAM_RAW);
        $mform->addHelpButton('text', 'interactiontext', 'mod_kaiiv');

        // Options, for the two types that offer a list.
        for ($index = 0; $index < \mod_kaiiv\timeline::MAX_OPTIONS; $index++) {
            $group = [
                $mform->createElement('text', 'option' . $index, '', ['size' => 44]),
                $mform->createElement('advcheckbox', 'correct' . $index, '',
                    get_string('authored:correct', 'mod_kaiiv')),
            ];
            $mform->addGroup($group, 'optiongroup' . $index,
                $index === 0 ? get_string('authored:options', 'mod_kaiiv') : '',
                ' ', false);
            $mform->setType('option' . $index, PARAM_TEXT);

            // One 'in' rule over every other type, not a 'neq' rule per option
            // type: hideIf rules are OR'ed, so "neq choice" and "neq
            // multichoice" together hide the options whatever is chosen.
            $mform->hideIf('optiongroup' . $index, 'type', 'in', $othertypes);
        }
        $mform->addHelpButton('optiongroup0', 'authored:options', 'mod_kaiiv');

        // True or false.
        $mform->addElement('select', 'istrue',
            get_string('authored:istrue', 'mod_kaiiv'), [
                '1' => get_string('istrue', 'mod_kaiiv'),
                '0' => get_string('isfalse', 'mod_kaiiv'),
            ]);
        $mform->hideIf('istrue', 'type', 'neq', 'truefalse');

        // Typed answers.
        $mform->addElement('textarea', 'accept',
            get_string('authored:accept', 'mod_kaiiv'),
            ['rows' => 4, 'cols' => 50]);
        $mform->setType('accept', PARAM_TEXT);
        $mform->addHelpButton('accept', 'authored:accept', 'mod_kaiiv');
        $mform->hideIf('accept', 'type', 'neq', 'shorttext');

        // Gaps, typed or dragged. One field for both, because the difference
        // between them is on screen and not in what the author writes.
        $mform->addElement('textarea', 'lines',
            get_string('authored:lines', 'mod_kaiiv'),
            ['rows' => 5, 'cols' => 60]);
        $mform->setType('lines', PARAM_TEXT);
        $mform->addHelpButton('lines', 'authored:lines', 'mod_kaiiv');
        $mform->hideIf('lines', 'type', 'in', [
            'choice', 'multichoice', 'truefalse', 'shorttext', 'marktheword',
            'label', 'image', 'link',
        ]);

        $mform->addElement('textarea', 'passage',
            get_string('authored:passage', 'mod_kaiiv'),
            ['rows' => 5, 'cols' => 60]);
        $mform->setType('passage', PARAM_TEXT);
        $mform->addHelpButton('passage', 'authored:passage', 'mod_kaiiv');
        $mform->hideIf('passage', 'type', 'neq', 'marktheword');

        // Image and link.
        $mform->addElement('url', 'url', get_string('authored:url', 'mod_kaiiv'),
            ['size' => 60], ['usefilepicker' => false]);
        $mform->setType('url', PARAM_URL);
        $mform->hideIf('url', 'type', 'in', [
            'choice', 'multichoice', 'truefalse', 'shorttext', 'blanks',
            'dragtext', 'marktheword', 'label',
        ]);

        $mform->addElement('text', 'alt', get_string('authored:alt', 'mod_kaiiv'),
            ['size' => 60]);
        $mform->setType('alt', PARAM_TEXT);
        $mform->addHelpButton('alt', 'authored:alt', 'mod_kaiiv');
        $mform->hideIf('alt', 'type', 'neq', 'image');

        $mform->addElement('text', 'caption',
            get_string('authored:caption', 'mod_kaiiv'), ['size' => 60]);
        $mform->setType('caption', PARAM_TEXT);
        $mform->hideIf('caption', 'type', 'neq', 'image');

        $mform->addElement('text', 'linktitle',
            get_string('authored:linktitle', 'mod_kaiiv'), ['size' => 60]);
        $mform->setType('linktitle', PARAM_TEXT);
        $mform->hideIf('linktitle', 'type', 'neq', 'link');

        // ---- after answering ---------------------------------------------
        $mform->addElement('editor', 'feedback',
            get_string('feedback', 'mod_kaiiv'), ['rows' => 3]);
        $mform->setType('feedback', PARAM_RAW);
        $mform->addHelpButton('feedback', 'feedback', 'mod_kaiiv');

        // ---- how it sits on the video ------------------------------------
        $mform->addElement('header', 'appearance',
            get_string('appearance', 'mod_kaiiv'));

        $mform->addElement('select', 'displaytype',
            get_string('displaytype', 'mod_kaiiv'), [
                'poster' => get_string('display:poster', 'mod_kaiiv'),
                'button' => get_string('display:button', 'mod_kaiiv'),
            ]);
        $mform->setDefault('displaytype', 'poster');
        $mform->addHelpButton('displaytype', 'displaytype', 'mod_kaiiv');

        $mform->addElement('text', 'endtime',
            get_string('endtime', 'mod_kaiiv'), ['size' => 8]);
        $mform->setType('endtime', PARAM_FLOAT);
        $mform->addHelpButton('endtime', 'endtime', 'mod_kaiiv');
        // Only the kinds that do not stop the video have a duration. The rest
        // end when they are answered, and a field offering to end one after
        // twelve seconds would be offering to let a learner wait it out.
        $mform->hideIf('endtime', 'type', 'in', [
            'choice', 'multichoice', 'truefalse', 'shorttext', 'blanks',
            'dragtext', 'marktheword',
        ]);

        foreach ([
            'x' => 20, 'y' => 20, 'width' => 60, 'height' => 40,
        ] as $name => $default) {
            $mform->addElement('text', $name,
                get_string('position:' . $name, 'mod_kaiiv'), ['size' => 5]);
            $mform->setType($name, PARAM_FLOAT);
            $mform->setDefault($name, $default);
            $mform->setAdvanced($name);
        }

        $this->add_action_buttons(true, get_string('saveinteraction', 'mod_kaiiv'));
    }

    /**
     * @param array $data
     * @param array $files
     * @return array
     */
    public function validation($data, $files) {
        $errors = parent::validation($data, $files);

        if (($data['starttime'] ?? 0) < 0) {
            $errors['starttime'] = get_string('error:negativetime', 'mod_kaiiv');
        }

        // Everything else about the content — an option with nothing ticked,
        // a gap exercise with no gaps in it — is checked by the engine, which
        // is the thing that knows what each type needs. Repeating those rules
        // here would be two lists to keep in step, and the engine's messages
        // already say what to fix.
        return $errors;
    }

    /**
     * Accepted answers, one per line.
     *
     * @param string $raw
     * @return array
     */
    public static function accepted_lines(string $raw): array {
        $lines = preg_split('/\R/u', $raw) ?: [];
        $lines = array_map('trim', $lines);
        return array_values(array_filter($lines, 'strlen'));
    }
}

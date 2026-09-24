<?php
// The activity module's obligations to Moodle core.
//
// Nearly the same file as mod_kaivideo's, because these are core's
// requirements rather than ours and they do not vary by what the activity
// does. The one real difference is the grade: there it is worked out in PHP,
// here it is asked of the engine — see kaiiv_update_grades().

defined('MOODLE_INTERNAL') || die();

/**
 * @param string $feature
 * @return mixed
 */
function kaiiv_supports($feature) {
    switch ($feature) {
        case FEATURE_MOD_INTRO:
        case FEATURE_SHOW_DESCRIPTION:
        case FEATURE_BACKUP_MOODLE2:
        case FEATURE_GRADE_HAS_GRADE:
        case FEATURE_COMPLETION_TRACKS_VIEWS:
        case FEATURE_COMPLETION_HAS_RULES:
            return true;
        case FEATURE_GROUPS:
        case FEATURE_GROUPINGS:
            return false;

        // FEATURE_BACKUP_MOODLE2 above is only safe because backup/moodle2/
        // exists. Declaring it without those four classes does not degrade
        // gracefully: every course containing one of these activities fails
        // to back up at all, with `Class "backup_kaiiv_activity_task" not
        // found`. A core feature broken by an activity that behaves perfectly
        // in every other way, with nothing in its own behaviour to hint at it.
        //
        // mod_kaivideo shipped exactly that once, and it was found by running
        // a real backup rather than by reading anything. If those classes are
        // ever removed, this line has to go with them in the same change.
        case FEATURE_MOD_PURPOSE:
            return MOD_PURPOSE_CONTENT;
        default:
            return null;
    }
}

/**
 * @param stdClass $data from mod_form
 * @param mixed $mform
 * @return int
 */
function kaiiv_add_instance($data, $mform = null) {
    global $DB;

    kaiiv_settle_source($data);

    $data->timecreated = time();
    $data->timemodified = time();
    $data->id = $DB->insert_record('kaiiv', $data);

    kaiiv_save_video_file($data);
    kaiiv_grade_item_update($data);
    return $data->id;
}

/**
 * @param stdClass $data from mod_form
 * @param mixed $mform
 * @return bool
 */
function kaiiv_update_instance($data, $mform = null) {
    global $DB;

    kaiiv_settle_source($data);

    $data->id = $data->instance;
    $data->timemodified = time();
    $DB->update_record('kaiiv', $data);

    kaiiv_save_video_file($data);
    kaiiv_grade_item_update($data);
    return true;
}

/**
 * Make sure exactly one source survives the save.
 *
 * An uploaded file and a typed address can both be sitting in the form — an
 * author who uploaded a video and then switched to a URL still has the file in
 * their draft area. Whichever they did not choose is cleared here, so the
 * record and the file area cannot end up describing two different videos.
 *
 * @param stdClass $data
 */
function kaiiv_settle_source($data) {
    $chosen = $data->sourcetype ?? (empty($data->videofile) ? 'url' : \mod_kaiiv\source::FILE);

    if ($chosen === 'url') {
        $data->videofile = 0;
        return;
    }

    // The address column is emptied rather than left to go stale: source::url()
    // falls back to it whenever no file is present, and a leftover address
    // would silently become the video again if the file were ever removed.
    $data->videourl = '';
}

/**
 * Move the uploaded video out of the draft area, or clear what is there.
 *
 * @param stdClass $data with coursemodule and videofile
 */
function kaiiv_save_video_file($data) {
    // Global because mod_form.php reads $CFG at its top level, and inside a
    // function it would otherwise see nothing. The editing page has already
    // loaded the form, which hid this; creating the activity any other way —
    // a script, an admin tool, a test generator — failed on the include.
    global $CFG;

    if (empty($data->coursemodule)) {
        return;
    }

    require_once($CFG->dirroot . '/course/moodleform_mod.php');
    require_once(__DIR__ . '/mod_form.php');
    $context = context_module::instance($data->coursemodule);

    if (empty($data->videofile)) {
        get_file_storage()->delete_area_files($context->id, 'mod_kaiiv',
            \mod_kaiiv\source::AREA, 0);
        return;
    }

    file_save_draft_area_files($data->videofile, $context->id, 'mod_kaiiv',
        \mod_kaiiv\source::AREA, 0, mod_kaiiv_mod_form::filemanager_options());
}

/**
 * Serve the uploaded video.
 *
 * @param stdClass $course
 * @param stdClass $cm
 * @param context $context
 * @param string $filearea
 * @param array $args
 * @param bool $forcedownload
 * @param array $options
 * @return bool false when it is not ours to serve
 */
function kaiiv_pluginfile($course, $cm, $context, $filearea, $args,
        $forcedownload, array $options = []) {
    if ($context->contextlevel != CONTEXT_MODULE
            || $filearea !== \mod_kaiiv\source::AREA) {
        return false;
    }

    // Enrolment is checked, not just login: a course video is course material,
    // and a URL that plays for anybody with an account is a URL that will be
    // passed around.
    require_login($course, true, $cm);
    if (!has_capability('mod/kaiiv:view', $context)) {
        return false;
    }

    // The itemid is the first thing in $args, not something to add back: it is
    // part of the address core has already split up for us.
    $itemid = (int) array_shift($args);
    $file = get_file_storage()->get_file_by_hash(sha1(
        "/{$context->id}/mod_kaiiv/" . \mod_kaiiv\source::AREA
        . "/{$itemid}/" . implode('/', $args)));
    if (!$file || $file->is_directory()) {
        return false;
    }

    // Never forced as a download, whatever was asked for. This file exists to
    // be played in a <video> element, and Moodle only byte-serves — which is
    // what makes seeking work at all — when it is not sending an attachment.
    send_stored_file($file, DAYSECS, 0, false, $options);
    return true;
}

/**
 * @param int $id instance id
 * @return bool
 */
function kaiiv_delete_instance($id) {
    global $DB;

    $activity = $DB->get_record('kaiiv', ['id' => $id]);
    if (!$activity) {
        return false;
    }

    // Responses first: they reference interactions, and leaving them behind
    // would keep somebody's answers after the activity holding them is gone.
    $interactions = $DB->get_fieldset_select('kaiiv_interaction', 'id',
        'kaiivid = ?', [$id]);
    if ($interactions) {
        $DB->delete_records_list('kaiiv_response', 'interactionid', $interactions);
    }
    $DB->delete_records('kaiiv_interaction', ['kaiivid' => $id]);
    $DB->delete_records('kaiiv_bookmark', ['kaiivid' => $id]);
    $DB->delete_records('kaiiv_progress', ['kaiivid' => $id]);
    $DB->delete_records('kaiiv', ['id' => $id]);

    grade_update('mod/kaiiv', $activity->course, 'mod', 'kaiiv', $id, 0, null,
        ['deleted' => 1]);
    return true;
}

/**
 * Create or update the gradebook item.
 *
 * @param stdClass $activity
 * @param mixed $grades
 * @return int
 */
function kaiiv_grade_item_update($activity, $grades = null) {
    global $CFG;
    require_once($CFG->libdir . '/gradelib.php');

    $params = ['itemname' => $activity->name];
    if ((int) $activity->grade > 0) {
        $params['gradetype'] = GRADE_TYPE_VALUE;
        $params['grademax'] = (int) $activity->grade;
        $params['grademin'] = 0;
    } else {
        $params['gradetype'] = GRADE_TYPE_NONE;
    }

    return grade_update('mod/kaiiv', $activity->course, 'mod', 'kaiiv',
        $activity->id, 0, $grades, $params);
}

/**
 * Push one learner's grade, or everybody's.
 *
 * The score comes from the engine, which means this can fail in a way the
 * kaivideo version cannot: the engine may be unreachable. When it is, the
 * learner is skipped rather than given a zero.
 *
 * A zero would be written to the gradebook, would look exactly like a real
 * zero, and would stay there after the outage ended — because nothing would
 * know to come back and recompute it. Skipping leaves the previous grade
 * standing, which is at worst out of date by one run of the task that called
 * this, and cron calls it again.
 *
 * @param stdClass $activity
 * @param int $userid 0 for all
 */
function kaiiv_update_grades($activity, $userid = 0) {
    global $DB;

    if ((int) $activity->grade <= 0) {
        kaiiv_grade_item_update($activity);
        return;
    }

    $userids = $userid
        ? [$userid]
        : $DB->get_fieldset_select('kaiiv_progress', 'DISTINCT userid',
            'kaiivid = ?', [$activity->id]);

    $grades = [];
    foreach ($userids as $id) {
        $score = \mod_kaiiv\responses::score($activity, (int) $id);
        if (empty($score['ok'])) {
            debugging('kaiiv: no grade for user ' . $id . ' on activity '
                . $activity->id . ': ' . ($score['error'] ?? 'unknown'),
                DEBUG_NORMAL);
            continue;
        }
        $grades[$id] = (object) [
            'userid' => $id,
            'rawgrade' => $score['fraction'] * (int) $activity->grade,
        ];
    }

    if ($grades) {
        kaiiv_grade_item_update($activity, $grades);
    } else {
        kaiiv_grade_item_update($activity);
    }
}

/**
 * What the course cache holds about one of these.
 *
 * Without this, the completion checkboxes appear on the form, save happily,
 * and are then never evaluated: core reads the enabled rules out of the cached
 * module info, and a module that does not publish them is a module with no
 * custom rules as far as completion is concerned. The symptom is a rule that
 * silently does nothing, which is worse than one that visibly fails.
 *
 * This was a real bug in mod_kaivideo, found by writing the test rather than
 * by reading the documentation. It is here from the start for that reason.
 *
 * @param stdClass $coursemodule
 * @return cached_cm_info|bool
 */
function kaiiv_get_coursemodule_info($coursemodule) {
    global $DB;

    $activity = $DB->get_record('kaiiv', ['id' => $coursemodule->instance],
        'id, name, intro, introformat, completionanswerall, completionwatched');
    if (!$activity) {
        return false;
    }

    $info = new cached_cm_info();
    $info->name = $activity->name;

    if ($coursemodule->showdescription) {
        $info->content = format_module_intro('kaiiv', $activity,
            $coursemodule->id, false);
    }

    // Only when the activity is set to automatic completion: publishing the
    // rules otherwise would have core evaluating conditions the teacher chose
    // to decide by hand.
    if ($coursemodule->completion == COMPLETION_TRACKING_AUTOMATIC) {
        $info->customdata['customcompletionrules']['completionanswerall'] =
            (int) $activity->completionanswerall;
        $info->customdata['customcompletionrules']['completionwatched'] =
            (int) $activity->completionwatched;
    }

    return $info;
}

/**
 * The activity's own menu.
 *
 * @param settings_navigation $settings
 * @param navigation_node $node
 */
function kaiiv_extend_settings_navigation($settings, $node) {
    global $PAGE;

    $context = $PAGE->cm->context;

    if (has_capability('mod/kaiiv:editinteractions', $context)) {
        $node->add(
            get_string('editinteractions', 'mod_kaiiv'),
            new moodle_url('/mod/kaiiv/edit.php', ['cmid' => $PAGE->cm->id]),
            navigation_node::TYPE_SETTING,
            null,
            'mod_kaiiv_edit',
            new pix_icon('t/edit', '')
        );
    }

    // Offered separately from editing: a teacher who may read results but not
    // rewrite questions is a normal arrangement, and gating the whole menu on
    // editing hides the report from exactly those people.
    if (has_capability('mod/kaiiv:viewreport', $context)) {
        $node->add(
            get_string('report', 'mod_kaiiv'),
            new moodle_url('/mod/kaiiv/report.php', ['cmid' => $PAGE->cm->id]),
            navigation_node::TYPE_SETTING,
            null,
            'mod_kaiiv_report',
            new pix_icon('i/report', '')
        );
    }
}

<?php
// What this activity knows about a person, and how to hand it over or remove it.
//
// Two tables hold learner data: what they answered, and how far they watched.
// The uploaded video is course material and holds nothing about anybody.
//
// The engine is declared too, as an external location. It stores nothing — it
// marks an answer and forgets it — but a privacy statement that lists only
// local tables is incomplete the moment an answer is sent somewhere to be
// judged, and "it does not keep it" is a claim that belongs in the statement
// rather than instead of it.

namespace mod_kaiiv\privacy;

defined('MOODLE_INTERNAL') || die();

use core_privacy\local\metadata\collection;
use core_privacy\local\request\approved_contextlist;
use core_privacy\local\request\approved_userlist;
use core_privacy\local\request\contextlist;
use core_privacy\local\request\transform;
use core_privacy\local\request\userlist;
use core_privacy\local\request\writer;

class provider implements
        \core_privacy\local\metadata\provider,
        \core_privacy\local\request\core_userlist_provider,
        \core_privacy\local\request\plugin\provider {

    /**
     * @param collection $collection
     * @return collection
     */
    public static function get_metadata(collection $collection): collection {
        $collection->add_database_table('kaiiv_response', [
            'userid' => 'privacy:metadata:kaiiv_response:userid',
            'response' => 'privacy:metadata:kaiiv_response:response',
            'attempt' => 'privacy:metadata:kaiiv_response:attempt',
            'correct' => 'privacy:metadata:kaiiv_response:correct',
            'timecreated' => 'privacy:metadata:kaiiv_response:timecreated',
        ], 'privacy:metadata:kaiiv_response');

        $collection->add_database_table('kaiiv_progress', [
            'userid' => 'privacy:metadata:kaiiv_progress:userid',
            'furthest' => 'privacy:metadata:kaiiv_progress:furthest',
            'finished' => 'privacy:metadata:kaiiv_progress:finished',
            'timemodified' => 'privacy:metadata:kaiiv_progress:timemodified',
        ], 'privacy:metadata:kaiiv_progress');

        $collection->add_external_location_link('kaiiv_engine', [
            'response' => 'privacy:metadata:kaiiv_engine:response',
        ], 'privacy:metadata:kaiiv_engine');

        $collection->add_subsystem_link('core_files', [],
            'privacy:metadata:filepurpose');

        return $collection;
    }

    /**
     * @param int $userid
     * @return contextlist
     */
    public static function get_contexts_for_userid(int $userid): contextlist {
        $contextlist = new contextlist();

        // Both tables, unioned rather than joined. A learner who opened a
        // video and answered nothing still has a progress row, and a
        // contextlist built from responses alone would tell them we hold
        // nothing about an activity we do hold something about.
        $sql = "SELECT ctx.id
                  FROM {context} ctx
                  JOIN {course_modules} cm ON cm.id = ctx.instanceid
                                          AND ctx.contextlevel = :modlevel
                  JOIN {modules} m ON m.id = cm.module AND m.name = 'kaiiv'
                  JOIN {kaiiv} k ON k.id = cm.instance
             LEFT JOIN {kaiiv_interaction} i ON i.kaiivid = k.id
             LEFT JOIN {kaiiv_response} r ON r.interactionid = i.id
                                         AND r.userid = :userid1
             LEFT JOIN {kaiiv_progress} p ON p.kaiivid = k.id
                                         AND p.userid = :userid2
                 WHERE r.id IS NOT NULL OR p.id IS NOT NULL";

        $contextlist->add_from_sql($sql, [
            'modlevel' => CONTEXT_MODULE,
            'userid1' => $userid,
            'userid2' => $userid,
        ]);

        return $contextlist;
    }

    /**
     * @param userlist $userlist
     */
    public static function get_users_in_context(userlist $userlist) {
        $context = $userlist->get_context();
        if (!$context instanceof \context_module) {
            return;
        }

        $userlist->add_from_sql('userid', "
            SELECT r.userid
              FROM {course_modules} cm
              JOIN {modules} m ON m.id = cm.module AND m.name = 'kaiiv'
              JOIN {kaiiv_interaction} i ON i.kaiivid = cm.instance
              JOIN {kaiiv_response} r ON r.interactionid = i.id
             WHERE cm.id = :cmid", ['cmid' => $context->instanceid]);

        $userlist->add_from_sql('userid', "
            SELECT p.userid
              FROM {course_modules} cm
              JOIN {modules} m ON m.id = cm.module AND m.name = 'kaiiv'
              JOIN {kaiiv_progress} p ON p.kaiivid = cm.instance
             WHERE cm.id = :cmid", ['cmid' => $context->instanceid]);
    }

    /**
     * @param approved_contextlist $contextlist
     */
    public static function export_user_data(approved_contextlist $contextlist) {
        global $DB;

        $userid = $contextlist->get_user()->id;

        foreach ($contextlist->get_contexts() as $context) {
            if (!$context instanceof \context_module) {
                continue;
            }

            $cm = get_coursemodule_from_id('kaiiv', $context->instanceid);
            if (!$cm) {
                continue;
            }

            $answers = [];
            foreach (\mod_kaiiv\responses::history((int) $cm->instance, $userid) as $row) {
                $answers[] = [
                    'attempt' => (int) $row->attempt,
                    // Decoded, because a person asking what we hold about them
                    // is owed their answer and not our transport format.
                    'response' => json_decode((string) $row->response, true),
                    'topic' => (string) $row->category,
                    'correct' => transform::yesno($row->correct),
                    'answered' => transform::datetime($row->timecreated),
                ];
            }

            $progress = $DB->get_record('kaiiv_progress',
                ['kaiivid' => $cm->instance, 'userid' => $userid]);

            writer::with_context($context)->export_data([], (object) [
                'answers' => $answers,
                'watchedto' => $progress ? (float) $progress->furthest : 0,
                'reachedtheend' => $progress
                    ? transform::yesno($progress->finished) : transform::yesno(0),
            ]);
        }
    }

    /**
     * @param \context $context
     */
    public static function delete_data_for_all_users_in_context(\context $context) {
        global $DB;

        if (!$context instanceof \context_module) {
            return;
        }
        $cm = get_coursemodule_from_id('kaiiv', $context->instanceid);
        if (!$cm) {
            return;
        }

        $interactions = $DB->get_fieldset_select('kaiiv_interaction', 'id',
            'kaiivid = ?', [$cm->instance]);
        if ($interactions) {
            $DB->delete_records_list('kaiiv_response', 'interactionid', $interactions);
        }
        $DB->delete_records('kaiiv_progress', ['kaiivid' => $cm->instance]);
    }

    /**
     * @param approved_contextlist $contextlist
     */
    public static function delete_data_for_user(approved_contextlist $contextlist) {
        global $DB;

        $userid = $contextlist->get_user()->id;

        foreach ($contextlist->get_contexts() as $context) {
            if (!$context instanceof \context_module) {
                continue;
            }
            $cm = get_coursemodule_from_id('kaiiv', $context->instanceid);
            if (!$cm) {
                continue;
            }

            self::delete_for($cm->instance, [$userid]);
        }
    }

    /**
     * @param approved_userlist $userlist
     */
    public static function delete_data_for_users(approved_userlist $userlist) {
        $context = $userlist->get_context();
        if (!$context instanceof \context_module) {
            return;
        }
        $cm = get_coursemodule_from_id('kaiiv', $context->instanceid);
        if (!$cm) {
            return;
        }

        self::delete_for($cm->instance, $userlist->get_userids());
    }

    /**
     * Remove some people's answers from one activity.
     *
     * The interactions themselves stay. They are the teacher's content, and
     * deleting a learner's data must not delete the question they answered
     * out from under everybody else.
     *
     * @param int $kaiivid
     * @param array $userids
     */
    protected static function delete_for(int $kaiivid, array $userids): void {
        global $DB;

        if (!$userids) {
            return;
        }

        [$insql, $params] = $DB->get_in_or_equal($userids, SQL_PARAMS_NAMED);

        $interactions = $DB->get_fieldset_select('kaiiv_interaction', 'id',
            'kaiivid = ?', [$kaiivid]);
        if ($interactions) {
            [$idsql, $idparams] = $DB->get_in_or_equal($interactions,
                SQL_PARAMS_NAMED, 'i');
            $DB->delete_records_select('kaiiv_response',
                "userid $insql AND interactionid $idsql",
                array_merge($params, $idparams));
        }

        $params['kaiivid'] = $kaiivid;
        $DB->delete_records_select('kaiiv_progress',
            "kaiivid = :kaiivid AND userid $insql", $params);
    }
}

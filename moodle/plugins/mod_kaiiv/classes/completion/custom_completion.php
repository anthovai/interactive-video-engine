<?php
// The two completion rules, and what each one actually asks.
//
// They are separate because they are failed differently: somebody who answers
// everything but stops five minutes from the end, and somebody who leaves the
// video playing in another tab and answers nothing.

namespace mod_kaiiv\completion;

defined('MOODLE_INTERNAL') || die();

use core_completion\activity_custom_completion;

class custom_completion extends activity_custom_completion {

    /**
     * @param string $rule
     * @return int
     */
    public function get_state(string $rule): int {
        global $DB;

        $this->validate_rule($rule);

        $userid = (int) $this->userid;
        $kaiivid = (int) $this->cm->instance;

        if ($rule === 'completionwatched') {
            $finished = $DB->get_field('kaiiv_progress', 'finished',
                ['kaiivid' => $kaiivid, 'userid' => $userid]);
            return $finished ? COMPLETION_COMPLETE : COMPLETION_INCOMPLETE;
        }

        // completionanswerall.
        //
        // Counted here rather than asked of the engine, because this is a
        // question about our own records — how many rows exist, and how many
        // of them this learner has touched — and not a question about rules.
        // Sending it to the engine would make course completion depend on the
        // engine being up, which is a much worse failure than a slightly
        // duplicated count.
        $total = $DB->count_records('kaiiv_interaction', ['kaiivid' => $kaiivid]);
        if ($total === 0) {
            // A timeline with nothing on it cannot be worked through. Complete
            // rather than incomplete: the alternative is an activity nobody
            // can ever finish, which is not what an author who has not added
            // questions yet meant to publish.
            return COMPLETION_COMPLETE;
        }

        // Every interaction, not only the marked ones. A caption is a stop on
        // the way through, and a learner who never reached it has not been
        // through the video — which is what this rule is about, unlike the
        // grade, which counts only what can be got wrong.
        $answered = $DB->count_records_sql(
            "SELECT COUNT(DISTINCT r.interactionid)
               FROM {kaiiv_response} r
               JOIN {kaiiv_interaction} i ON i.id = r.interactionid
              WHERE i.kaiivid = :kaiivid AND r.userid = :userid",
            ['kaiivid' => $kaiivid, 'userid' => $userid]);

        return $answered >= $total ? COMPLETION_COMPLETE : COMPLETION_INCOMPLETE;
    }

    /**
     * @return array
     */
    public static function get_defined_custom_rules(): array {
        return ['completionanswerall', 'completionwatched'];
    }

    /**
     * @return array
     */
    public function get_custom_rule_descriptions(): array {
        return [
            'completionanswerall' => get_string('completionanswerall_desc', 'mod_kaiiv'),
            'completionwatched' => get_string('completionwatched_desc', 'mod_kaiiv'),
        ];
    }

    /**
     * @return array
     */
    public function get_sort_order(): array {
        return [
            'completionview',
            'completionanswerall',
            'completionwatched',
            'completionusegrade',
        ];
    }
}

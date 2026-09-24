<?php
// The record: what each learner answered, every time they answered it.
//
// This file writes things down. It does not decide anything — the engine does
// that, and it is asked on every submission rather than consulted once and
// cached, because a cached verdict is a verdict that outlives the rule that
// produced it.
//
// Every attempt is kept. The grade uses the most recent one, but a teacher
// asking "did they guess twice and then get it" has to be able to find out,
// and a table that overwrites cannot answer that.

namespace mod_kaiiv;

defined('MOODLE_INTERNAL') || die();

class responses {

    /**
     * Record one answer and say what it was worth.
     *
     * @param int $interactionid
     * @param int $userid
     * @param mixed $response what the browser sent, already decoded
     * @return array the engine's verdict, or ok=false with a code
     */
    public static function answer(int $interactionid, int $userid,
            $response): array {
        global $DB;

        $interaction = timeline::one_for_engine($interactionid);
        $activity = $DB->get_record('kaiiv',
            ['id' => $interaction['kaiivid']], '*', MUST_EXIST);

        $attempts = self::attempts_so_far($interactionid, $userid);

        // Sent so the engine can refuse, and it has to be able to: the score
        // reads the latest response, so an answer marked after the last
        // attempt — or after a correct one, once the answer has been shown —
        // would replace the one that counted. The web service is callable
        // directly, so the player not offering another go is no guarantee.
        $answeredcorrectly = $DB->record_exists('kaiiv_response', [
            'interactionid' => $interactionid,
            'userid' => $userid,
            'correct' => 1,
        ]);

        $verdict = engine::judge($interaction, $response, $attempts,
            timeline::rules($activity), $answeredcorrectly);

        if (empty($verdict['ok'])) {
            // Nothing is written. A response the engine could not mark is not
            // a wrong answer — recording it as one would spend an attempt on
            // an outage, and the learner would have no way to tell the
            // difference.
            return $verdict;
        }

        $DB->insert_record('kaiiv_response', (object) [
            'interactionid' => $interactionid,
            'userid' => $userid,
            // The engine says what is worth storing, which is not always what
            // arrived: typed text comes back folded, chosen options sorted.
            // A report that cannot group "Bangkok" and "  bangkok" as one
            // answer is a report that says two people said two things.
            'response' => json_encode($verdict['store'], JSON_UNESCAPED_UNICODE),
            // Copied from the interaction as it stands now, not read back
            // through it later. Recategorising a question between cohorts is
            // an ordinary thing to do, and it must not change what a past
            // report says about a topic somebody was already marked on.
            'category' => $interaction['category'],
            'attempt' => (int) $verdict['attempts'],
            'correct' => !empty($verdict['correct']) ? 1 : 0,
            'timecreated' => time(),
        ]);

        return $verdict;
    }

    /**
     * What this learner has done, in the shape the engine reads.
     *
     * Keyed by interaction id as a string, because that is what it becomes in
     * JSON either way and a key that changes type in transit is a key that
     * misses.
     *
     * @param int $kaiivid
     * @param int $userid
     * @return array
     */
    public static function seen(int $kaiivid, int $userid): array {
        global $DB;

        $records = $DB->get_records_sql(
            "SELECT r.id, r.interactionid, r.response, r.correct
               FROM {kaiiv_response} r
               JOIN {kaiiv_interaction} i ON i.id = r.interactionid
              WHERE i.kaiivid = :kaiivid AND r.userid = :userid
           ORDER BY r.id ASC",
            ['kaiivid' => $kaiivid, 'userid' => $userid]);

        // Ascending, overwriting: the last row for an interaction wins, which
        // is the most recent answer. Counted in the same pass, so the attempt
        // total does not need a query per interaction.
        $seen = [];
        foreach ($records as $record) {
            $key = (string) (int) $record->interactionid;
            $seen[$key] = [
                'response' => json_decode((string) $record->response, true),
                'correct' => (bool) $record->correct,
                'attempts' => isset($seen[$key]) ? $seen[$key]['attempts'] + 1 : 1,
            ];
        }

        return $seen;
    }

    /**
     * @param int $interactionid
     * @param int $userid
     * @return int
     */
    public static function attempts_so_far(int $interactionid, int $userid): int {
        global $DB;

        return $DB->count_records('kaiiv_response', [
            'interactionid' => $interactionid,
            'userid' => $userid,
        ]);
    }

    /**
     * The learner's score.
     *
     * @param \stdClass $activity
     * @param int $userid
     * @return array ok/correct/total/fraction, or ok=false with a code
     */
    public static function score(\stdClass $activity, int $userid): array {
        return engine::score(
            timeline::for_engine((int) $activity->id),
            self::seen((int) $activity->id, $userid));
    }

    /**
     * Everything one learner has answered, for the privacy provider and for
     * the teacher report.
     *
     * Unlike seen(), this keeps every attempt. The two exist separately
     * because they answer different questions — "where is this learner up to"
     * and "what did this learner do" — and a function that tried to answer
     * both would have to pick one to be wrong about.
     *
     * @param int $kaiivid
     * @param int $userid
     * @return array rows
     */
    public static function history(int $kaiivid, int $userid): array {
        global $DB;

        return $DB->get_records_sql(
            "SELECT r.*
               FROM {kaiiv_response} r
               JOIN {kaiiv_interaction} i ON i.id = r.interactionid
              WHERE i.kaiivid = :kaiivid AND r.userid = :userid
           ORDER BY r.timecreated ASC, r.id ASC",
            ['kaiivid' => $kaiivid, 'userid' => $userid]);
    }
}

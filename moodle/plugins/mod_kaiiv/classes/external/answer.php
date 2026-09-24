<?php
// Submitting one answer.
//
// The response arrives as a JSON string rather than a typed structure, because
// what an answer looks like depends on the kind of question: a list of option
// indexes, a typed string, a map of gap to word, a boolean. Moodle's external
// API describes one shape per parameter, so describing all of them would mean
// four optional parameters of which three are always null — and a new question
// type would mean a new parameter and a new version of this function.
//
// So it is a string here, and the engine is the thing that knows how to read
// it. That is the same division as everywhere else in this plugin: the
// platform carries, the engine decides.

namespace mod_kaiiv\external;

defined('MOODLE_INTERNAL') || die();

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_single_structure;
use core_external\external_value;

class answer extends external_api {

    /**
     * @return external_function_parameters
     */
    public static function execute_parameters(): external_function_parameters {
        return new external_function_parameters([
            'cmid' => new external_value(PARAM_INT, 'course module id'),
            'interactionid' => new external_value(PARAM_INT, 'which interaction'),
            'response' => new external_value(PARAM_RAW,
                'the answer, JSON encoded; its shape depends on the type'),
        ]);
    }

    /**
     * @param int $cmid
     * @param int $interactionid
     * @param string $response
     * @return array
     */
    public static function execute(int $cmid, int $interactionid,
            string $response): array {
        global $CFG, $DB, $USER;

        // The module's lib.php is not autoloaded, and an external function is
        // the least likely place for it to have been pulled in by something
        // else: an AJAX request loads almost nothing. kaiiv_update_grades()
        // below lives there.
        require_once($CFG->dirroot . '/mod/kaiiv/lib.php');

        [
            'cmid' => $cmid,
            'interactionid' => $interactionid,
            'response' => $response,
        ] = self::validate_parameters(self::execute_parameters(), [
            'cmid' => $cmid,
            'interactionid' => $interactionid,
            'response' => $response,
        ]);

        [$course, $cm] = get_course_and_cm_from_cmid($cmid, 'kaiiv');
        $context = \context_module::instance($cm->id);
        self::validate_context($context);
        require_capability('mod/kaiiv:answer', $context);

        // The interaction has to belong to the activity the caller named.
        // Without this, an id from another course would be marked against
        // whatever question it happened to be — and the capability check above
        // would have passed, because it is about this activity.
        $interaction = $DB->get_record('kaiiv_interaction',
            ['id' => $interactionid, 'kaiivid' => $cm->instance], 'id', MUST_EXIST);

        // Decoded to objects, not associative arrays. With `true`, PHP turns
        // {"0": "a", "1": "b"} — the shape a gap answer has — into an array
        // with integer keys, and json_encode then sends it on as ["a", "b"].
        // The shape of an answer is the question type's business, so this
        // layer carries it through as it arrived.
        $verdict = \mod_kaiiv\responses::answer((int) $interaction->id,
            (int) $USER->id, json_decode($response));

        if (empty($verdict['ok'])) {
            // Reported as a failure the player can show, not thrown. An
            // exception here reaches the browser as a generic web service
            // error, and the learner needs to be told the specific thing that
            // is true: their attempt was not used up.
            return [
                'ok' => false,
                'error' => (string) ($verdict['error'] ?? 'unknown'),
                'correct' => false,
                'revealed' => false,
                'mayretry' => true,
                'attempts' => 0,
                'answers' => '[]',
                'feedback' => '',
            ];
        }

        // Completion and the gradebook are updated here rather than by a
        // scheduled task, because a learner who finishes the last question
        // and sees the activity still marked incomplete will answer it again.
        $activity = $DB->get_record('kaiiv', ['id' => $cm->instance], '*', MUST_EXIST);
        $completion = new \completion_info($course);
        if ($completion->is_enabled($cm)) {
            $completion->update_state($cm, COMPLETION_UNKNOWN, (int) $USER->id);
        }
        kaiiv_update_grades($activity, (int) $USER->id);

        return [
            'ok' => true,
            'error' => '',
            'correct' => (bool) $verdict['correct'],
            'revealed' => (bool) $verdict['revealed'],
            'mayretry' => (bool) $verdict['may_retry'],
            'attempts' => (int) $verdict['attempts'],
            // JSON for the same reason the response is: the shape of an answer
            // is the question type's business, not this function's.
            'answers' => json_encode($verdict['answers'], JSON_UNESCAPED_UNICODE),
            'feedback' => (string) $verdict['feedback'],
        ];
    }

    /**
     * @return external_single_structure
     */
    public static function execute_returns(): external_single_structure {
        return new external_single_structure([
            'ok' => new external_value(PARAM_BOOL, 'whether it was marked at all'),
            'error' => new external_value(PARAM_ALPHANUMEXT, 'why not, if not'),
            'correct' => new external_value(PARAM_BOOL, 'whether it was right'),
            'revealed' => new external_value(PARAM_BOOL,
                'whether the answer and explanation are in this reply'),
            'mayretry' => new external_value(PARAM_BOOL, 'whether another go remains'),
            'attempts' => new external_value(PARAM_INT, 'attempts used including this one'),
            'answers' => new external_value(PARAM_RAW,
                'the correct answer, JSON encoded — empty unless revealed'),
            'feedback' => new external_value(PARAM_RAW,
                'the explanation — empty unless revealed'),
        ]);
    }
}

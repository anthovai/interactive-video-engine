<?php
// Where the learner has got to.
//
// Called every fifteen seconds while playing, and again when the page is about
// to go away. The second of those is why the furthest point is kept rather
// than the latest: the two calls can arrive in either order, and a beacon sent
// at pagehide may land after the periodic one that followed it.
//
// Keeping the furthest makes that harmless, and makes sending it twice
// harmless too — which is the only reason the player can afford to fire on
// both visibilitychange and pagehide without either of them needing to know
// about the other.

namespace mod_kaiiv\external;

defined('MOODLE_INTERNAL') || die();

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_single_structure;
use core_external\external_value;

class record_progress extends external_api {

    /**
     * @return external_function_parameters
     */
    public static function execute_parameters(): external_function_parameters {
        return new external_function_parameters([
            'cmid' => new external_value(PARAM_INT, 'course module id'),
            'position' => new external_value(PARAM_FLOAT, 'seconds into the video'),
            'finished' => new external_value(PARAM_BOOL, 'whether the end was reached'),
        ]);
    }

    /**
     * @param int $cmid
     * @param float $position
     * @param bool $finished
     * @return array
     */
    public static function execute(int $cmid, float $position,
            bool $finished): array {
        global $DB, $USER;

        [
            'cmid' => $cmid,
            'position' => $position,
            'finished' => $finished,
        ] = self::validate_parameters(self::execute_parameters(), [
            'cmid' => $cmid,
            'position' => $position,
            'finished' => $finished,
        ]);

        [$course, $cm] = get_course_and_cm_from_cmid($cmid, 'kaiiv');
        $context = \context_module::instance($cm->id);
        self::validate_context($context);
        require_capability('mod/kaiiv:view', $context);

        // A position below zero is not a reading, it is a bug or a forgery,
        // and clamping is better than refusing: the learner is watching a
        // video and does not need an error about it.
        $position = max(0.0, (float) $position);

        $existing = $DB->get_record('kaiiv_progress',
            ['kaiivid' => $cm->instance, 'userid' => $USER->id]);

        if (!$existing) {
            $DB->insert_record('kaiiv_progress', (object) [
                'kaiivid' => $cm->instance,
                'userid' => $USER->id,
                'furthest' => $position,
                'finished' => $finished ? 1 : 0,
                'timemodified' => time(),
            ]);
        } else {
            $DB->update_record('kaiiv_progress', (object) [
                'id' => $existing->id,
                // Never rewound by watching again. A learner who scrubs back
                // to re-watch a section has not unwatched the rest of it.
                'furthest' => max((float) $existing->furthest, $position),
                // Same direction: once the end has been reached, it has been.
                'finished' => ($existing->finished || $finished) ? 1 : 0,
                'timemodified' => time(),
            ]);
        }

        $completion = new \completion_info($course);
        if ($completion->is_enabled($cm)) {
            $completion->update_state($cm, COMPLETION_UNKNOWN, (int) $USER->id);
        }

        return ['ok' => true];
    }

    /**
     * @return external_single_structure
     */
    public static function execute_returns(): external_single_structure {
        return new external_single_structure([
            'ok' => new external_value(PARAM_BOOL, 'recorded'),
        ]);
    }
}

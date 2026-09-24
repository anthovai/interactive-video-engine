<?php
// What the class did, for the person who has to do something about it.
//
// Three tables, and the order they appear in is the argument.
//
// By question comes first, hardest first, because "18 of 20 picked option 3 at
// 04:12" is not a fact about those eighteen people. It is a fact about the
// four minutes of video before it, and it is the only thing on this page that
// says what to go and change.
//
// By topic comes second: one question everybody misses is usually a badly
// worded question, but a whole topic sitting at 40% is a section that did not
// teach what it was meant to.
//
// By learner comes last. It is the table everybody asks for, and it says that
// some people did better than others, which the teacher already knew.
//
// Counted from our own rows rather than asked of the engine. The engine marks
// one answer at a time and holds nothing; a report is arithmetic over what we
// stored, and routing it through a network call would make a teacher's report
// depend on a service being up to tell us what is already in our database.

namespace mod_kaiiv;

defined('MOODLE_INTERNAL') || die();

class report {

    /** A question most of the class got wrong is worth a flag. */
    const STRUGGLE_BELOW = 0.5;

    /**
     * @param int $kaiivid
     * @param \context $context
     * @return array for the template
     */
    public static function build(int $kaiivid, \context $context): array {
        $interactions = timeline::interactions($kaiivid);
        $graded = array_filter($interactions, static function($row) {
            return self::is_graded((string) $row->type);
        });

        return [
            'byquestion' => self::by_question($graded),
            'bycategory' => self::by_category($graded),
            'bylearner' => self::by_learner($kaiivid, $context, count($graded)),
            'nobodyyet' => !self::anybody($kaiivid),
        ];
    }

    /**
     * @param int $kaiivid
     * @return bool
     */
    protected static function anybody(int $kaiivid): bool {
        global $DB;

        return $DB->record_exists('kaiiv_progress', ['kaiivid' => $kaiivid]);
    }

    /**
     * One row per question, hardest first.
     *
     * The latest attempt per learner is what counts, which is the same rule
     * the grade uses. Counting every attempt would make a question look harder
     * the more chances people were given at it.
     *
     * @param array $interactions
     * @return array
     */
    protected static function by_question(array $interactions): array {
        global $DB;

        $rows = [];

        foreach ($interactions as $interaction) {
            $latest = $DB->get_records_sql(
                "SELECT r.userid, r.response, r.correct
                   FROM {kaiiv_response} r
                  WHERE r.interactionid = :id
               ORDER BY r.id ASC", ['id' => $interaction->id]);

            $byuser = [];
            foreach ($latest as $one) {
                $byuser[(int) $one->userid] = $one;
            }

            $answered = count($byuser);
            $correct = 0;
            $wrong = [];

            foreach ($byuser as $one) {
                if ($one->correct) {
                    $correct++;
                    continue;
                }
                $said = (string) $one->response;
                $wrong[$said] = ($wrong[$said] ?? 0) + 1;
            }

            arsort($wrong);
            $content = json_decode((string) $interaction->content, true) ?: [];

            $rows[] = [
                'starttime' => timeline::clock((float) $interaction->starttime),
                'type' => timeline::type_label((string) $interaction->type),
                'question' => self::text_of($content),
                'category' => (string) $interaction->category,
                'answered' => $answered,
                'correct' => $correct,
                'share' => $answered ? round($correct / $answered * 100) : null,
                'struggled' => $answered
                    && ($correct / $answered) < self::STRUGGLE_BELOW,
                // The commonest wrong answer, which is usually a
                // misunderstanding worth explaining rather than a question
                // worth rewording.
                'commonestwrong' => $wrong
                    ? self::describe_response(
                        (string) array_key_first($wrong), $content,
                        (string) $interaction->type)
                    : '',
            ];
        }

        // Hardest first. A report ordered by time buries its problem in the
        // middle of the table.
        usort($rows, static function($a, $b) {
            return ($a['share'] ?? 101) <=> ($b['share'] ?? 101);
        });

        return $rows;
    }

    /**
     * One row per topic, weakest first.
     *
     * Read off the response's own category column rather than the
     * interaction's. They are usually the same; when they are not, it is
     * because somebody recategorised a question after these answers were
     * given, and what this table reports is what the cohort was measured on
     * at the time.
     *
     * @param array $interactions
     * @return array
     */
    protected static function by_category(array $interactions): array {
        global $DB;

        if (!$interactions) {
            return [];
        }

        [$insql, $params] = $DB->get_in_or_equal(
            array_keys($interactions), SQL_PARAMS_NAMED);

        $rows = $DB->get_records_sql(
            "SELECT r.id, r.userid, r.interactionid, r.category, r.correct
               FROM {kaiiv_response} r
              WHERE r.interactionid $insql
           ORDER BY r.id ASC", $params);

        // Latest attempt per learner per question, then grouped.
        $latest = [];
        foreach ($rows as $row) {
            $latest[$row->userid . ':' . $row->interactionid] = $row;
        }

        $totals = [];
        foreach ($latest as $row) {
            $key = (string) $row->category;
            if (!isset($totals[$key])) {
                $totals[$key] = ['answered' => 0, 'correct' => 0];
            }
            $totals[$key]['answered']++;
            if ($row->correct) {
                $totals[$key]['correct']++;
            }
        }

        $out = [];
        foreach ($totals as $name => $total) {
            $out[] = [
                'category' => $name !== ''
                    ? $name : get_string('report:uncategorised', 'mod_kaiiv'),
                'answered' => $total['answered'],
                'correct' => $total['correct'],
                'share' => round($total['correct'] / $total['answered'] * 100),
            ];
        }

        usort($out, static fn($a, $b) => $a['share'] <=> $b['share']);
        return $out;
    }

    /**
     * One row per learner.
     *
     * @param int $kaiivid
     * @param \context $context
     * @param int $total how many questions can be answered
     * @return array
     */
    protected static function by_learner(int $kaiivid, \context $context,
            int $total): array {
        global $DB;

        $progress = $DB->get_records('kaiiv_progress', ['kaiivid' => $kaiivid]);
        if (!$progress) {
            return [];
        }

        $counts = $DB->get_records_sql(
            "SELECT r.userid, r.interactionid, r.correct, r.id
               FROM {kaiiv_response} r
               JOIN {kaiiv_interaction} i ON i.id = r.interactionid
              WHERE i.kaiivid = :kaiivid
           ORDER BY r.id ASC", ['kaiivid' => $kaiivid]);

        $latest = [];
        foreach ($counts as $row) {
            $latest[$row->userid . ':' . $row->interactionid] = $row;
        }

        $peruser = [];
        foreach ($latest as $row) {
            $id = (int) $row->userid;
            if (!isset($peruser[$id])) {
                $peruser[$id] = ['answered' => 0, 'correct' => 0];
            }
            $peruser[$id]['answered']++;
            if ($row->correct) {
                $peruser[$id]['correct']++;
            }
        }

        $users = $DB->get_records_list('user', 'id', array_keys($progress)
            ? array_column($progress, 'userid') : [0]);

        $out = [];
        foreach ($progress as $row) {
            $userid = (int) $row->userid;
            $seen = $peruser[$userid] ?? ['answered' => 0, 'correct' => 0];

            $out[] = [
                'name' => isset($users[$userid])
                    ? fullname($users[$userid])
                    : get_string('unknownuser'),
                'answered' => $seen['answered'],
                'total' => $total,
                'correct' => $seen['correct'],
                'share' => $total ? round($seen['correct'] / $total * 100) : null,
                'furthest' => timeline::clock((float) $row->furthest),
                'finished' => (bool) $row->finished,
            ];
        }

        \core_collator::asort_array_of_arrays_by_key($out, 'name');
        return array_values($out);
    }

    /**
     * @param array $content
     * @return string
     */
    protected static function text_of(array $content): string {
        return shorten_text(
            html_to_text((string) ($content['text'] ?? ''), 0, false), 120);
    }

    /**
     * Turn a stored response back into something a teacher can read.
     *
     * Option indexes are the awkward case: "[2]" tells nobody anything, and
     * the whole value of this column is recognising the misunderstanding.
     *
     * @param string $stored
     * @param array $content
     * @param string $type
     * @return string
     */
    protected static function describe_response(string $stored, array $content,
            string $type): string {
        $decoded = json_decode($stored, true);

        if ($type === 'choice' || $type === 'multichoice') {
            $options = (array) ($content['options'] ?? []);
            $picked = array_map(static function($index) use ($options) {
                return (string) ($options[(int) $index] ?? $index);
            }, (array) $decoded);
            return $picked ? implode(', ', $picked)
                : get_string('report:blank', 'mod_kaiiv');
        }

        if ($type === 'truefalse') {
            return $decoded
                ? get_string('istrue', 'mod_kaiiv')
                : get_string('isfalse', 'mod_kaiiv');
        }

        if (is_array($decoded)) {
            return implode(', ', array_map('strval', $decoded));
        }

        $said = trim((string) ($decoded ?? $stored));
        return $said !== '' ? $said : get_string('report:blank', 'mod_kaiiv');
    }

    /**
     * Whether a type is one the engine marks.
     *
     * Asked of the engine's catalogue and cached for the request rather than
     * hard-coded. The list of types belongs to kaiiv-service/app/types.py, and
     * a second copy in a report is a second copy that can disagree about
     * whether a caption counts towards a score.
     *
     * Falls back to "not marked" when the engine cannot be reached, which
     * leaves a report with no questions in it rather than one with captions
     * counted as questions. A visibly empty report is a better failure than a
     * quietly wrong one.
     *
     * @param string $type
     * @return bool
     */
    protected static function is_graded(string $type): bool {
        static $graded = null;

        if ($graded === null) {
            $graded = [];
            $catalogue = engine::types();
            if (!empty($catalogue['ok'])) {
                foreach ($catalogue['types'] as $entry) {
                    $graded[$entry['type']] = !empty($entry['graded']);
                }
            }
        }

        return !empty($graded[$type]);
    }
}

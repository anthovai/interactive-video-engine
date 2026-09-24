<?php
// The timeline, as this platform stores it.
//
// Reading rows and handing them to the engine. There is no marking here, no
// answer-stripping here, and no rule about what a learner may see here — all
// three live in kaiiv-service, and a second copy of any of them in this file
// would be a second copy that can disagree with the first.
//
// The one thing that is genuinely ours is the shape of the rows: which columns
// exist, and how a Moodle file area becomes a video URL. That is platform
// knowledge, and it is exactly what the engine refuses to hold.

namespace mod_kaiiv;

defined('MOODLE_INTERNAL') || die();

class timeline {

    /**
     * Every interaction on one activity, in the order an author arranged them.
     *
     * @param int $kaiivid
     * @return array rows from kaiiv_interaction
     */
    public static function interactions(int $kaiivid): array {
        global $DB;

        return $DB->get_records('kaiiv_interaction', ['kaiivid' => $kaiivid],
            'starttime ASC, sortorder ASC, id ASC');
    }

    /**
     * @param int $kaiivid
     * @return array rows from kaiiv_bookmark
     */
    public static function bookmarks(int $kaiivid): array {
        global $DB;

        return array_values(array_map(function(\stdClass $row) {
            return [
                'at' => (float) $row->attime,
                'label' => (string) $row->label,
            ];
        }, $DB->get_records('kaiiv_bookmark', ['kaiivid' => $kaiivid],
            'attime ASC, id ASC')));
    }

    /**
     * The rows in the shape the engine reads them.
     *
     * JSON columns are decoded here rather than passed through as strings,
     * because the engine's contract is a payload and not a database dump —
     * and because a caller in another language should not have to know that
     * this one happened to store them encoded.
     *
     * @param int $kaiivid
     * @return array
     */
    public static function for_engine(int $kaiivid): array {
        $out = [];

        foreach (self::interactions($kaiivid) as $row) {
            $out[] = [
                'id' => (int) $row->id,
                'type' => (string) $row->type,
                'start' => (float) $row->starttime,
                'end' => (float) $row->endtime,
                'display' => (string) $row->displaytype,
                'pauses' => (bool) $row->pausevideo,
                'x' => (float) $row->x,
                'y' => (float) $row->y,
                'width' => (float) $row->width,
                'height' => (float) $row->height,
                'label' => (string) $row->label,
                'content' => json_decode((string) $row->content, true) ?: [],
                'answers' => json_decode((string) $row->answers, true) ?: [],
                'feedback' => (string) $row->feedback,
            ];
        }

        return $out;
    }

    /**
     * One interaction, in the same shape.
     *
     * @param int $interactionid
     * @return array
     */
    public static function one_for_engine(int $interactionid): array {
        global $DB;

        $row = $DB->get_record('kaiiv_interaction', ['id' => $interactionid],
            '*', MUST_EXIST);

        return [
            'id' => (int) $row->id,
            'type' => (string) $row->type,
            'content' => json_decode((string) $row->content, true) ?: [],
            'answers' => json_decode((string) $row->answers, true) ?: [],
            'feedback' => (string) $row->feedback,
            'category' => (string) $row->category,
            'kaiivid' => (int) $row->kaiivid,
        ];
    }

    /**
     * The rules the engine applies to this activity.
     *
     * A snapshot of the settings as they stand, sent with every call rather
     * than configured on the engine. The engine serves more than one activity
     * and, before long, more than one platform; a rule stored there would be
     * a rule that has to be kept in step with a row here.
     *
     * @param \stdClass $activity
     * @return array
     */
    public static function rules(\stdClass $activity): array {
        return [
            'allowreview' => (bool) $activity->allowreview,
            'maxattempts' => (int) $activity->maxattempts,
        ];
    }

    /**
     * What this learner may see.
     *
     * @param \stdClass $activity
     * @param int $userid
     * @return array ok/items, or ok=false with a code
     */
    public static function for_player(\stdClass $activity, int $userid): array {
        return engine::timeline(
            self::for_engine((int) $activity->id),
            responses::seen((int) $activity->id, $userid),
            self::rules($activity));
    }

    // ----------------------------------------------------------------------
    // Authoring
    // ----------------------------------------------------------------------

    /** How many options one choice question may offer. */
    const MAX_OPTIONS = 6;

    /**
     * Two interactions closer together than this both pause the video in the
     * same moment, and the second one opens on top of the first.
     *
     * Only enforced between interactions that actually pause. Two captions at
     * the same second are a layout the author chose; two questions are an
     * accident nobody meant.
     */
    const MIN_GAP = 0.5;

    /**
     * Create or update one interaction.
     *
     * The authored form — the one with the answers written between asterisks
     * — is sent to the engine and never stored. What comes back is the two
     * halves, and they go into two columns.
     *
     * @param int $kaiivid
     * @param array $fields as gathered by edit.php
     * @param int|null $id existing interaction, or null to create
     * @return array ok, or ok=false with a code and a detail to show the author
     */
    public static function save(int $kaiivid, array $fields, ?int $id = null): array {
        global $DB;

        $split = engine::author((string) $fields['type'], $fields['authored']);
        if (empty($split['ok'])) {
            return $split;
        }

        $starttime = max(0.0, (float) $fields['starttime']);

        if (!empty($split['pauses'])
                && self::collides($kaiivid, $starttime, $id)) {
            return [
                'ok' => false,
                'error' => 'tooclose',
                'detail' => get_string('error:tooclose', 'mod_kaiiv'),
            ];
        }

        $record = (object) [
            'kaiivid' => $kaiivid,
            'starttime' => $starttime,
            // An interaction that pauses ends when it is answered rather than
            // when a clock runs out, so its window is a moment. Anything else
            // stays on screen for as long as the author said — and for
            // DEFAULT_DURATION when they said nothing, because an empty "until"
            // field used to store endtime = starttime, a window of zero
            // seconds, and a caption with no window is never on screen at all.
            'endtime' => $split['pauses']
                ? $starttime
                : self::window_end($starttime, (float) ($fields['endtime'] ?? 0)),
            'type' => (string) $fields['type'],
            'displaytype' => $split['graded'] && $split['pauses']
                // Forced. A question the learner can decline to open is not a
                // question the video can refuse to continue past, and the
                // display setting is an authoring convenience rather than a
                // licence to skip an assessment.
                ? 'poster' : (string) ($fields['displaytype'] ?? 'poster'),
            'pausevideo' => $split['pauses'] ? 1 : 0,
            'x' => (float) ($fields['x'] ?? 20),
            'y' => (float) ($fields['y'] ?? 20),
            'width' => (float) ($fields['width'] ?? 60),
            'height' => (float) ($fields['height'] ?? 40),
            'label' => (string) ($fields['label'] ?? ''),
            'category' => (string) ($fields['category'] ?? ''),
            'content' => json_encode($split['content'], JSON_UNESCAPED_UNICODE),
            'answers' => json_encode($split['answers'], JSON_UNESCAPED_UNICODE),
            'feedback' => (string) ($fields['feedback'] ?? ''),
            'sortorder' => (int) ($fields['sortorder'] ?? 0),
        ];

        if ($id) {
            $record->id = $id;
            $DB->update_record('kaiiv_interaction', $record);
        } else {
            $record->timecreated = time();
            $record->id = $DB->insert_record('kaiiv_interaction', $record);
        }

        return ['ok' => true, 'id' => (int) $record->id];
    }

    /** How long something that does not stop the video stays on screen when
     *  the author gave no end. Long enough to read a line. */
    const DEFAULT_DURATION = 5.0;

    /**
     * When a non-pausing interaction leaves the screen.
     *
     * @param float $start
     * @param float $end what the author typed, 0 when they left it empty
     * @return float
     */
    public static function window_end(float $start, float $end): float {
        return $end > $start ? $end : $start + self::DEFAULT_DURATION;
    }

    /**
     * @param int $kaiivid
     * @param float $at
     * @param int|null $ignore the interaction being edited
     * @return bool whether something that pauses is already there
     */
    protected static function collides(int $kaiivid, float $at, ?int $ignore): bool {
        global $DB;

        $params = [
            'kaiivid' => $kaiivid,
            'low' => $at - self::MIN_GAP,
            'high' => $at + self::MIN_GAP,
        ];
        $where = 'kaiivid = :kaiivid AND pausevideo = 1
                  AND starttime > :low AND starttime < :high';
        if ($ignore) {
            $where .= ' AND id <> :ignore';
            $params['ignore'] = $ignore;
        }

        return $DB->record_exists_select('kaiiv_interaction', $where, $params);
    }

    /**
     * Remove one interaction and everything answered against it.
     *
     * The responses go too. Keeping them would leave rows pointing at a
     * question nobody can read, which is not a record of anything — and a
     * report that counts them would be counting answers to a question that no
     * longer exists.
     *
     * @param int $id
     */
    public static function delete(int $id): void {
        global $DB;

        $DB->delete_records('kaiiv_response', ['interactionid' => $id]);
        $DB->delete_records('kaiiv_interaction', ['id' => $id]);
    }

    /**
     * The timeline as the editing screen lists it.
     *
     * Answers are summarised rather than printed. An author looking at the
     * list wants to see which question is which; the answer itself is on the
     * editing form, one click away, where being on screen is the point.
     *
     * @param int $kaiivid
     * @return array
     */
    public static function for_editing(int $kaiivid): array {
        $out = [];

        foreach (self::interactions($kaiivid) as $row) {
            $content = json_decode((string) $row->content, true) ?: [];
            $answers = json_decode((string) $row->answers, true) ?: [];

            $out[] = [
                'id' => (int) $row->id,
                'type' => (string) $row->type,
                'typelabel' => self::type_label((string) $row->type),
                'starttime' => (float) $row->starttime,
                'startlabel' => self::clock((float) $row->starttime),
                'label' => (string) $row->label,
                'category' => (string) $row->category,
                'summary' => self::summarise($content),
                'answercount' => count($answers),
                'pauses' => (bool) $row->pausevideo,
            ];
        }

        return $out;
    }

    /**
     * @param string $type
     * @return string
     */
    public static function type_label(string $type): string {
        $key = 'type:' . $type;
        $manager = get_string_manager();
        // A type the engine has and this plugin has no label for shows its own
        // name rather than a missing-string placeholder. The list of types is
        // the engine's, and a language pack that has not caught up should not
        // make the editing screen unreadable.
        return $manager->string_exists($key, 'mod_kaiiv')
            ? get_string($key, 'mod_kaiiv') : $type;
    }

    /**
     * A one-line version of whatever this interaction holds.
     *
     * @param array $content
     * @return string
     */
    protected static function summarise(array $content): string {
        foreach (['text', 'title', 'caption', 'url'] as $key) {
            if (!empty($content[$key])) {
                return shorten_text(html_to_text((string) $content[$key], 0, false), 90);
            }
        }
        return '';
    }

    /**
     * Seconds as a clock, because an author reads one off the video controls.
     *
     * @param float $seconds
     * @return string
     */
    public static function clock(float $seconds): string {
        $seconds = max(0, (int) round($seconds));
        return sprintf('%02d:%02d', intdiv($seconds, 60), $seconds % 60);
    }

    /**
     * Topics already used on this video, to offer back to the author.
     *
     * Offered rather than enforced, so the same topic does not end up spelled
     * two ways and counted twice in the report.
     *
     * @param int $kaiivid
     * @return array
     */
    public static function categories(int $kaiivid): array {
        global $DB;

        $used = $DB->get_fieldset_select('kaiiv_interaction', 'DISTINCT category',
            'kaiivid = ? AND category <> ?', [$kaiivid, '']);
        sort($used, SORT_NATURAL | SORT_FLAG_CASE);
        return $used;
    }
}

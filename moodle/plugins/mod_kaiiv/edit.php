<?php
// Building the timeline.
//
// The video is on the same page as the form on purpose: an author choosing
// "ask this at 01:24" needs to see what is on screen at 01:24, and a form on
// its own turns that into arithmetic against a separate tab.
//
// The authored text — the one with answers written between asterisks and
// ticks against the right option — is assembled here and handed to the
// engine, which splits it. Nothing on this page stores it, and nothing on
// this page decides what a learner may see: both belong to the service.

require_once(__DIR__ . '/../../config.php');
// Required explicitly. A module's lib.php is not autoloaded — Moodle includes
// it when core needs one of the hooks, not because a page in the module
// directory is running — and kaiiv_update_grades() below is in it. Without
// this the first save on a fresh install dies with "undefined function",
// which reads like a missing file rather than a missing include.
require_once(__DIR__ . '/lib.php');
require_once(__DIR__ . '/edit_form.php');

$cmid = required_param('cmid', PARAM_INT);
$delete = optional_param('delete', 0, PARAM_INT);
$edit = optional_param('edit', 0, PARAM_INT);

[$course, $cm] = get_course_and_cm_from_cmid($cmid, 'kaiiv');
require_login($course, true, $cm);

$context = context_module::instance($cm->id);
require_capability('mod/kaiiv:editinteractions', $context);

$activity = $DB->get_record('kaiiv', ['id' => $cm->instance], '*', MUST_EXIST);
$url = new moodle_url('/mod/kaiiv/edit.php', ['cmid' => $cmid]);

$PAGE->set_url($url);
$PAGE->set_context($context);
$PAGE->set_title(get_string('editinteractions', 'mod_kaiiv'));
$PAGE->set_heading(format_string($activity->name));

if ($delete) {
    require_sesskey();
    // Scoped to this activity: an id from elsewhere must not be deletable by
    // somebody who happens to be able to edit this one.
    $row = $DB->get_record('kaiiv_interaction',
        ['id' => $delete, 'kaiivid' => $activity->id], 'id', MUST_EXIST);
    \mod_kaiiv\timeline::delete((int) $row->id);
    kaiiv_update_grades($activity);
    redirect($url, get_string('interactiondeleted', 'mod_kaiiv'), null,
        \core\output\notification::NOTIFY_SUCCESS);
}

// What kinds exist is the engine's answer, not ours.
//
// An editing screen that cannot reach the engine is shown rather than hidden,
// because the author needs to be told why they cannot add anything — and
// because the list of what is already there is worth seeing either way.
$catalogue = \mod_kaiiv\engine::types();
$enginefailed = empty($catalogue['ok']);

$types = [];
if (!$enginefailed) {
    foreach ($catalogue['types'] as $entry) {
        $types[$entry['type']] = \mod_kaiiv\timeline::type_label($entry['type']);
    }
}

$form = null;
if (!$enginefailed) {
    $form = new mod_kaiiv_edit_form($url, ['cmid' => $cmid, 'types' => $types]);
}

if ($form && $edit) {
    $record = $DB->get_record('kaiiv_interaction',
        ['id' => $edit, 'kaiivid' => $activity->id], '*', MUST_EXIST);
    $form->set_data(kaiiv_edit_prefill($record));
}

if ($form && $form->is_cancelled()) {
    redirect($url);
} else if ($form && ($data = $form->get_data())) {
    $authored = kaiiv_edit_authored($data);

    $result = \mod_kaiiv\timeline::save((int) $activity->id, [
        'starttime' => $data->starttime,
        'endtime' => $data->endtime ?? 0,
        'type' => $data->type,
        'displaytype' => $data->displaytype ?? 'poster',
        'label' => $data->label ?? '',
        'category' => $data->category ?? '',
        'feedback' => $data->feedback['text'] ?? '',
        'x' => $data->x ?? 20,
        'y' => $data->y ?? 20,
        'width' => $data->width ?? 60,
        'height' => $data->height ?? 40,
        'authored' => $authored,
    ], $data->interactionid ?: null);

    if (!empty($result['ok'])) {
        kaiiv_update_grades($activity);
        redirect($url, get_string('interactionsaved', 'mod_kaiiv'), null,
            \core\output\notification::NOTIFY_SUCCESS);
    }

    // Shown rather than thrown. These are authoring mistakes — no option
    // ticked, a gap exercise with no gaps — and the engine already says which
    // one in words an author can act on. Throwing would replace that with a
    // stack trace and lose everything they had typed.
    \core\notification::error(
        $result['detail'] ?: get_string('error:notsavedauthoring', 'mod_kaiiv'));
}

$videourl = \mod_kaiiv\source::url($activity, $context->id);
$sourceinfo = \mod_kaiiv\source::describe($videourl);

if ($sourceinfo['provider'] === \mod_kaiiv\source::HLS) {
    // The one source that cannot be declared in the markup. Same helper the
    // player uses, so one place knows how a stream gets onto a <video>.
    $PAGE->requires->js_call_amd('mod_kaiiv/backend', 'attachStream',
        ['[data-region="preview"]', $videourl]);
}

echo $OUTPUT->header();

if ($enginefailed) {
    \core\notification::error(get_string('error:enginedown', 'mod_kaiiv'));
}

// The preview keeps the provider's own controls, unlike the player: this page
// is for scrubbing around to find a frame, not for taking the lesson, and
// there is nothing here to skip past.
echo $OUTPUT->render_from_template('mod_kaiiv/edit', [
    'videourl' => $videourl,
    'isnative' => in_array($sourceinfo['provider'],
        \mod_kaiiv\source::NATIVE, true),
    'filesrc' => $sourceinfo['provider'] === \mod_kaiiv\source::FILE
        ? $videourl : '',
    'embedurl' => \mod_kaiiv\source::embed_url($sourceinfo),
    'items' => array_map(static function($item) use ($url) {
        $item['editurl'] = (new moodle_url($url, ['edit' => $item['id']]))->out(false);
        $item['deleteurl'] = (new moodle_url($url,
            ['delete' => $item['id'], 'sesskey' => sesskey()]))->out(false);
        return $item;
    }, \mod_kaiiv\timeline::for_editing((int) $activity->id)),
    'categories' => array_map(static fn($name) => ['name' => $name],
        \mod_kaiiv\timeline::categories((int) $activity->id)),
    'viewurl' => (new moodle_url('/mod/kaiiv/view.php', ['id' => $cmid]))->out(false),
]);

if ($form) {
    $form->display();
}

echo $OUTPUT->footer();

/**
 * Gather the fields this type uses into the shape the engine reads.
 *
 * Only the fields the chosen type uses are read. Every field exists on the
 * form at all times so that switching type loses nothing, which means fields
 * belonging to other types arrive filled in — and passing those on would have
 * the engine refusing a question because of something the author typed into a
 * box they were no longer looking at.
 *
 * @param stdClass $data
 * @return array
 */
function kaiiv_edit_authored(stdClass $data): array {
    $text = $data->text['text'] ?? '';

    switch ($data->type) {
        case 'choice':
        case 'multichoice':
            $options = [];
            for ($index = 0; $index < \mod_kaiiv\timeline::MAX_OPTIONS; $index++) {
                $option = trim((string) ($data->{'option' . $index} ?? ''));
                if ($option === '') {
                    // Blanks are dropped, and the tick that went with one is
                    // dropped with it. The indexes the engine receives count
                    // filled options only, so an author who leaves box 2 empty
                    // and ticks box 3 gets box 3 marked correct rather than
                    // whatever ends up in that position afterwards.
                    continue;
                }
                $options[] = [
                    'text' => $option,
                    'correct' => !empty($data->{'correct' . $index}),
                ];
            }
            return ['text' => $text, 'options' => $options];

        case 'truefalse':
            return ['text' => $text, 'correct' => !empty($data->istrue)];

        case 'shorttext':
            return [
                'text' => $text,
                'accept' => mod_kaiiv_edit_form::accepted_lines(
                    (string) ($data->accept ?? '')),
            ];

        case 'blanks':
        case 'dragtext':
            return [
                'text' => $text,
                'lines' => mod_kaiiv_edit_form::accepted_lines(
                    (string) ($data->lines ?? '')),
            ];

        case 'marktheword':
            return ['text' => $text, 'passage' => (string) ($data->passage ?? '')];

        case 'image':
            return [
                'url' => (string) ($data->url ?? ''),
                'alt' => (string) ($data->alt ?? ''),
                'caption' => (string) ($data->caption ?? ''),
            ];

        case 'link':
            return [
                'url' => (string) ($data->url ?? ''),
                'title' => (string) ($data->linktitle ?? ''),
            ];
    }

    // label, and anything the engine grows that this file has not caught up
    // with. Text is the one field every type has.
    return ['text' => $text];
}

/**
 * Fill the form in from a stored interaction.
 *
 * Only the public half is recoverable. `answers` is stored split out, and the
 * authored form it came from — `The capital of *France* is Paris` — was never
 * stored at all, so it is rebuilt here from the two halves.
 *
 * That rebuild is lossy in one direction and it is worth saying where: a gap
 * that accepted several spellings comes back with all of them, in the order
 * they were stored, which may not be the order they were typed.
 *
 * @param stdClass $record
 * @return stdClass
 */
function kaiiv_edit_prefill(stdClass $record): stdClass {
    $content = json_decode((string) $record->content, true) ?: [];
    $answers = json_decode((string) $record->answers, true) ?: [];

    $data = (object) [
        'interactionid' => (int) $record->id,
        'starttime' => (float) $record->starttime,
        'endtime' => (float) $record->endtime,
        'type' => (string) $record->type,
        'displaytype' => (string) $record->displaytype,
        'label' => (string) $record->label,
        'category' => (string) $record->category,
        'x' => (float) $record->x,
        'y' => (float) $record->y,
        'width' => (float) $record->width,
        'height' => (float) $record->height,
        'text' => ['text' => (string) ($content['text'] ?? ''), 'format' => FORMAT_HTML],
        'feedback' => ['text' => (string) $record->feedback, 'format' => FORMAT_HTML],
        'url' => (string) ($content['url'] ?? ''),
        'alt' => (string) ($content['alt'] ?? ''),
        'caption' => (string) ($content['caption'] ?? ''),
        'linktitle' => (string) ($content['title'] ?? ''),
    ];

    switch ($record->type) {
        case 'choice':
        case 'multichoice':
            foreach ((array) ($content['options'] ?? []) as $index => $option) {
                $data->{'option' . $index} = $option;
                $data->{'correct' . $index} =
                    in_array($index, array_map('intval', $answers), true) ? 1 : 0;
            }
            break;

        case 'truefalse':
            $data->istrue = !empty($answers[0]) ? '1' : '0';
            break;

        case 'shorttext':
            $data->accept = implode("\n", $answers);
            break;

        case 'blanks':
        case 'dragtext':
            $data->lines = kaiiv_edit_regap(
                (array) ($content['lines'] ?? []), $answers);
            break;

        case 'marktheword':
            $data->passage = kaiiv_edit_remark(
                (array) ($content['words'] ?? []), $answers);
            break;
    }

    return $data;
}

/**
 * Put the answers back into the gaps, so the author sees what they wrote.
 *
 * @param array $lines with [[n]] where a gap is
 * @param array $answers accepted spellings per gap
 * @return string
 */
function kaiiv_edit_regap(array $lines, array $answers): string {
    $filled = array_map(static function(string $line) use ($answers) {
        return preg_replace_callback('/\[\[(\d+)\]\]/', static function($match) use ($answers) {
            $words = (array) ($answers[(int) $match[1]] ?? []);
            return $words ? '*' . implode('/', $words) . '*' : '**';
        }, $line);
    }, $lines);

    return implode("\n", $filled);
}

/**
 * Put the asterisks back around the marked words.
 *
 * @param array $words the whole passage, one entry per word
 * @param array $answers indexes of the marked ones
 * @return string
 */
function kaiiv_edit_remark(array $words, array $answers): string {
    $marked = array_map('intval', $answers);

    return implode(' ', array_map(
        static function($word, $index) use ($marked) {
            return in_array($index, $marked, true) ? '*' . $word . '*' : $word;
        },
        $words, array_keys($words)));
}

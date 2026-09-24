<?php
// Watching it.
//
// The timeline is fetched from the engine here, on the server, and handed to
// the player as part of the page. The player never asks for it: a player that
// could request a timeline is a player a learner can request one from, with
// whatever parameters they like.

require_once(__DIR__ . '/../../config.php');

$cmid = required_param('id', PARAM_INT);

[$course, $cm] = get_course_and_cm_from_cmid($cmid, 'kaiiv');
require_login($course, true, $cm);

$context = context_module::instance($cm->id);
require_capability('mod/kaiiv:view', $context);

$activity = $DB->get_record('kaiiv', ['id' => $cm->instance], '*', MUST_EXIST);

$PAGE->set_url(new moodle_url('/mod/kaiiv/view.php', ['id' => $cmid]));
$PAGE->set_context($context);
$PAGE->set_title(format_string($activity->name));
$PAGE->set_heading(format_string($course->fullname));

$completion = new completion_info($course);
$completion->set_module_viewed($cm);

$canedit = has_capability('mod/kaiiv:editinteractions', $context);

// The address the player loads, which for an uploaded video is a pluginfile
// URL built against this context rather than anything stored on the record.
$videourl = \mod_kaiiv\source::url($activity, $context->id);
$sourceinfo = \mod_kaiiv\source::describe($videourl);

$progress = $DB->get_record('kaiiv_progress',
    ['kaiivid' => $activity->id, 'userid' => $USER->id]);

$timeline = \mod_kaiiv\timeline::for_player($activity, (int) $USER->id);

// An engine that is down is reported on the page and the video is not started.
//
// The tempting alternative is to play the video with no interactions on it,
// which looks like it degrades gracefully and does not: a learner watches the
// whole thing, is never asked anything, and finishes believing they are done.
// A video that will not start is a support call. A video that quietly drops
// the assessment is a cohort with no record of having been assessed.
$enginefailed = empty($timeline['ok']);
$items = $enginefailed ? [] : $timeline['items'];

$enginereason = '';
if ($enginefailed) {
    $reason = (string) ($timeline['error'] ?? 'unknown');
    debugging('kaiiv: engine unavailable on cmid ' . $cmid . ': ' . $reason
        . ' ' . (string) ($timeline['detail'] ?? ''), DEBUG_NORMAL);

    // Why, for the people who can do something about it. A learner sees the
    // same sentence whatever went wrong — they cannot fix any of it — but a
    // teacher or administrator told only "could not be reached" when the real
    // cause is a mismatched key goes and checks the firewall.
    if ($canedit || has_capability('moodle/site:config', context_system::instance())) {
        $known = ['bad_key' => 'error:badkey', 'not_configured' => 'error:notconfigured'];
        $enginereason = isset($known[$reason])
            ? get_string($known[$reason], 'mod_kaiiv')
            : get_string('error:enginereason', 'mod_kaiiv', s($reason . ': '
                . (string) ($timeline['detail'] ?? '')));
    }
}

// The kind, in words, for the marker a screen reader reads out.
//
// Added here rather than asked of the engine: what a type is called is a
// language question, and the engine holds no language. Without it the forked
// player builds its marker label from an undefined field and announces
// "Interaction. undefined" — which is worse than saying nothing, because it
// sounds like a fault rather than a missing word.
foreach ($items as $index => $item) {
    $items[$index]['typelabel'] =
        \mod_kaiiv\timeline::type_label((string) $item['type']);
}

$PAGE->requires->js_call_amd('mod_kaiiv/player', 'init', [[
    'cmid' => (int) $cm->id,
    'provider' => $sourceinfo['provider'],
    'videoid' => $sourceinfo['videoid'],
    // The address of a file or a stream. For a file it is also in the markup;
    // the player is given it anyway, because it builds that markup itself on
    // pages that are not this one and checks for it the same way on both.
    'src' => in_array($sourceinfo['provider'], \mod_kaiiv\source::NATIVE, true) ? $videourl : '',
    // The stream address, for the one backend that has to attach its source
    // rather than declare it in the markup.
    'streamurl' => $sourceinfo['provider'] === \mod_kaiiv\source::HLS ? $videourl : '',
    'items' => $items,
    'bookmarks' => $activity->showbookmarks
        ? \mod_kaiiv\timeline::bookmarks((int) $activity->id) : [],
    'mustanswer' => (bool) $activity->mustanswer,
    'allowreview' => (bool) $activity->allowreview,
    'maxattempts' => (int) $activity->maxattempts,
    'posterstart' => (bool) $activity->posterstart,
    'showendscreen' => (bool) $activity->showendscreen,
    'title' => format_string($activity->name),
    'resumeat' => $progress ? (float) $progress->furthest : 0.0,
]]);

echo $OUTPUT->header();

// The description is not printed here. Moodle's activity header already
// renders it, and printing it again puts the same paragraph on the page twice.

echo $OUTPUT->render_from_template('mod_kaiiv/player', [
    'videourl' => $videourl,
    'provider' => $sourceinfo['provider'],
    'isnative' => in_array($sourceinfo['provider'], \mod_kaiiv\source::NATIVE, true),
    'isyoutube' => ($sourceinfo['provider'] === \mod_kaiiv\source::YOUTUBE),
    'isvimeo' => ($sourceinfo['provider'] === \mod_kaiiv\source::VIMEO),
    // An HLS playlist is not a src: handing a .m3u8 to a <video> that cannot
    // decode it makes the browser report "no supported sources" before video.js
    // has had a chance to attach. It arrives through the config instead.
    'filesrc' => $sourceinfo['provider'] === \mod_kaiiv\source::FILE ? $videourl : '',
    // Questions, not interactions: telling a learner there are eight when
    // three of them are captions sets them up to expect a longer test.
    'questioncount' => count(array_filter($items,
        static fn($item) => !empty($item['graded']))),
    'enginefailed' => $enginefailed,
    'enginereason' => $enginereason,
    'canedit' => $canedit,
    'editurl' => (new moodle_url('/mod/kaiiv/edit.php', ['cmid' => $cm->id]))->out(false),
    'nointeractions' => !$enginefailed && empty($items),
]);

echo $OUTPUT->footer();

<?php
// Put one learner back to the start of one activity.
//
// For the browser check. An activity someone has already answered does not
// ask again, which is right for a learner and useless for a test that has to
// see each question arrive — so before each run their answers and their place
// in the video are removed, and nothing else is touched.
//
//     php mod/kaiiv/tests/reset_learner.php <cmid> <username>
//
// CLI only, and it refuses anything that is not one learner on one kaiiv
// activity, because the same two DELETEs with a wrong id would remove real
// learners' records.

define('CLI_SCRIPT', true);

require(__DIR__ . '/../../../config.php');

[$cmid, $username] = array_slice($argv, 1) + [null, null];
if (!$cmid || !$username) {
    cli_error('usage: reset_learner.php <cmid> <username>');
}

$cm = get_coursemodule_from_id('kaiiv', (int) $cmid, 0, false, MUST_EXIST);
$user = $DB->get_record('user', ['username' => $username, 'deleted' => 0], 'id', MUST_EXIST);

$interactions = $DB->get_fieldset_select('kaiiv_interaction', 'id',
    'kaiivid = ?', [$cm->instance]);

$removed = 0;
if ($interactions) {
    [$insql, $params] = $DB->get_in_or_equal($interactions, SQL_PARAMS_NAMED);
    $params['userid'] = $user->id;
    $removed = $DB->count_records_select('kaiiv_response',
        "userid = :userid AND interactionid $insql", $params);
    $DB->delete_records_select('kaiiv_response',
        "userid = :userid AND interactionid $insql", $params);
}
$DB->delete_records('kaiiv_progress', ['kaiivid' => $cm->instance, 'userid' => $user->id]);

mtrace("reset {$username} on cmid {$cmid}: {$removed} response(s) removed");

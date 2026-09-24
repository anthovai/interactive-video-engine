<?php
defined('MOODLE_INTERNAL') || die();

$string['pluginname'] = 'Interactive video (KAISER)';
$string['modulename'] = 'Interactive video (KAISER)';
$string['modulenameplural'] = 'Interactive videos (KAISER)';
$string['pluginadministration'] = 'Interactive video administration';
$string['noinstances'] = 'There are no interactive videos in this course.';
$string['modulename_help'] = 'Plays a video with things placed on top of it at times you choose — questions, captions, images and links. The video can be set to refuse to continue until a question is answered.

Questions are marked on the server. The correct answers are never sent to the browser before a learner has earned them, so they cannot be read out of the page.';

// ---- the video ------------------------------------------------------------
$string['sourcetype'] = 'Where the video comes from';
$string['sourcetype_help'] = '**Upload a file** puts the video into this Moodle. It is served to enrolled learners only, it goes into course backups, and it keeps working when nothing outside is reachable.

**Use an address** points at a YouTube or Vimeo link, or at a video file already hosted somewhere. Nothing is copied, so whoever controls that address controls whether the lesson plays.

Only one of the two is kept. Switching from one to the other clears what you had.';
$string['source:upload'] = 'Upload a file';
$string['source:url'] = 'Use an address';
$string['videofile'] = 'Video file';
$string['videofile_help'] = 'MP4 or WebM. Whatever the site allows as a maximum file size applies here, so a long recording may need to be uploaded by an administrator or linked instead.';
$string['videourl'] = 'Video address';
$string['videourl_help'] = 'A YouTube or Vimeo link, an HLS stream (.m3u8), or a direct link to a video file the browser can play. Not a page that contains a video: what plays has to be a real video element, which is also what lets proctoring watch it.

Nothing is copied into Moodle, so the lesson stops working whenever that address does, and it does not travel with a course backup.';

// ---- playback -------------------------------------------------------------
$string['playback'] = 'Playback';
$string['mustanswer'] = 'Must answer to continue';
$string['mustanswer_help'] = 'The video stops at each question and will not go past it until the learner answers. Seeking forward does not skip a question — it brings it up immediately.';
$string['posterstart'] = 'Show a start screen';
$string['showbookmarks'] = 'Show bookmarks';
$string['showendscreen'] = 'Show a summary at the end';
$string['showendscreen_help'] = 'A screen at the end of the video showing what the learner scored. The figures come from the server, which did the marking; nothing on this screen is worked out in the browser.';

// ---- answering ------------------------------------------------------------
$string['answering'] = 'Answering';
$string['allowreview'] = 'Allow another attempt at a question';
$string['allowreview_help'] = 'After a wrong answer, offer to try again. Every attempt is recorded; the most recent one counts.

While another attempt is available, a wrong answer is told only that it was wrong: the correct answer and the explanation are both held back. Releasing them and then offering a retry makes the second attempt free.';
$string['maxattempts'] = 'Attempts per question';
$string['maxattempts_help'] = 'How many times a learner may answer one question. On the last attempt — or when they get it right — the correct answer and the explanation are released.

Unlimited means the answer is only ever released by getting it right.';
$string['attempts:unlimited'] = 'Unlimited';

// ---- editing --------------------------------------------------------------
$string['editinteractions'] = 'Interactions on the timeline';
$string['addinteraction'] = 'Add an interaction';
$string['interactionsaved'] = 'Saved.';
$string['interactiondeleted'] = 'Deleted.';
$string['starttime'] = 'At (seconds)';
$string['starttime_help'] = 'How many seconds into the video this appears. Play the video above and read the time off the controls.';
$string['label'] = 'Label';
$string['label_help'] = 'Shown on the marker on the timeline, and read out by screen readers. Not the question itself: a marker that gives the question away before it is opened defeats the point.';
$string['category'] = 'Topic';
$string['category_help'] = 'What this is about — "Safety", "Quality", and so on. It goes on the interaction rather than on the video, because one video usually covers several topics, and a report that cannot separate them cannot say which topic a cohort is weak on.';
$string['feedback'] = 'Explanation after answering';
$string['feedback_help'] = 'Shown once the answer has been released — that is, when the learner gets it right or runs out of attempts.';
$string['backtovideo'] = 'Back to the video';

// ---- interaction types ----------------------------------------------------
// Kept in step with kaiiv-service/app/types.py, which is the list that
// decides. The editing screen asks the engine what exists rather than reading
// this file, so a name here that the engine does not have simply never
// appears.
$string['type'] = 'Kind of interaction';
$string['type:choice'] = 'One answer';
$string['type:multichoice'] = 'Several answers';
$string['type:truefalse'] = 'True or false';
$string['type:shorttext'] = 'Typed answer';
$string['type:blanks'] = 'Fill in the blanks';
$string['type:dragtext'] = 'Drag the words';
$string['type:marktheword'] = 'Mark the words';
$string['type:label'] = 'Caption';
$string['type:image'] = 'Image';
$string['type:link'] = 'Link';

$string['authored:options'] = 'Answers to choose between';
$string['authored:options_help'] = 'Fill in as many as you need and leave the rest empty; blanks are dropped. Tick the ones that are right. For a single-answer question, tick exactly one.';
$string['authored:accept'] = 'Accepted answers';
$string['authored:accept_help'] = 'One per line. Any of them counts as right.

Matching ignores extra spaces and English capitals, and nothing else. Thai tone marks and vowels are compared as typed, because treating ผู้ and ผู as the same word is accepting a misspelling rather than being lenient. To accept a variant, add it as its own line.';
$string['authored:lines'] = 'Sentences';
$string['authored:lines_help'] = 'One sentence per line. Wrap the word that goes in the gap in asterisks: `The capital of *France* is Paris`.

Several accepted spellings go inside the same asterisks, separated by a slash: `*France/francia*`.

The asterisks are never stored and never reach the browser — the answer is split out the moment you save.';
$string['authored:passage'] = 'Passage';
$string['authored:passage_help'] = 'The text the learner reads. Wrap the words they should mark in asterisks: `the *cat* sat on the *mat*`.

The learner sees the whole passage with every word markable, and the asterisks are not in it.';
$string['authored:correct'] = 'Correct';

// ---- the editing form -----------------------------------------------------
$string['placement'] = 'Where it goes';
$string['contentheader'] = 'What it says';
$string['appearance'] = 'How it sits on the video';
$string['interactiontext'] = 'Text';
$string['interactiontext_help'] = 'For a question, this is the question. For a caption, it is the caption. For an image or a link, it is the line above it — leave it empty if there is nothing to say.';
$string['saveinteraction'] = 'Save';
$string['stopsvideo'] = 'Stops the video';
$string['displaytype'] = 'How it appears';
$string['displaytype_help'] = '**On the video** draws it over the frame as soon as its moment arrives.

**As a marker** puts a button on the timeline that the learner opens when they choose.

Questions that stop the video are always drawn on the video, whatever is chosen here. A question the learner can decline to open is not a question the video can refuse to continue past.';
$string['display:poster'] = 'On the video';
$string['display:button'] = 'As a marker';
$string['endtime'] = 'Until (seconds)';
$string['endtime_help'] = 'When it leaves the screen. Only for the kinds that do not stop the video — the rest end when they are answered, and a duration on one of those would be an offer to wait it out.';
$string['position:x'] = 'Left (%)';
$string['position:y'] = 'Top (%)';
$string['position:width'] = 'Width (%)';
$string['position:height'] = 'Height (%)';
$string['authored:istrue'] = 'The statement is';
$string['authored:url'] = 'Address';
$string['authored:alt'] = 'Description for screen readers';
$string['authored:alt_help'] = 'What somebody who cannot see the image needs to know. Leave it empty if the image is decoration — an invented description is worse than none.';
$string['authored:caption'] = 'Caption';
$string['authored:linktitle'] = 'Link text';
$string['error:negativetime'] = 'An interaction cannot be placed before the video starts.';
$string['error:tooclose'] = 'Something that stops the video is already at almost the same moment. Move one of them.';
$string['error:notsavedauthoring'] = 'That could not be saved. Check the fields for this kind of interaction.';

// ---- player ---------------------------------------------------------------
$string['nointeractions'] = 'This video has nothing on its timeline yet.';
$string['questioncount'] = '{$a} question(s) on this video';
$string['correct'] = 'Correct';
$string['wrong'] = 'Not quite';
$string['continue'] = 'Continue';
$string['tryagain'] = 'Try again';
$string['submitanswer'] = 'Submit';
$string['youranswer'] = 'Your answer';
$string['play'] = 'Play';
$string['pause'] = 'Pause';
$string['back10'] = 'Back 10s';
$string['attemptsleft'] = '{$a} attempt(s) left';
$string['istrue'] = 'True';
$string['isfalse'] = 'False';
$string['pickatleastone'] = 'Tick at least one answer before submitting.';
$string['unsupportedtype'] = 'This kind of interaction cannot be shown by this version of the player. Tell whoever administers the site.';
$string['interactionword'] = 'Interaction';

// ---- failures -------------------------------------------------------------
// Named rather than generic, because every one of these means something
// different to whoever has to fix it, and "something went wrong" sends a
// teacher to us instead of to the setting they can change themselves.
$string['error:enginereason'] = 'For teachers and administrators: {$a}. Check the engine address and key under Site administration → Plugins → Activity modules → Interactive video (KAISER).';
$string['error:notconfigured'] = 'The interactive video engine has no address configured. An administrator needs to set it before this activity can be used.';
$string['error:badkey'] = 'The interactive video engine rejected our key. The shared secret here and the one on the engine do not match.';
$string['error:enginedown'] = 'The interactive video engine could not be reached, so the questions on this video cannot be shown. Nothing has been lost — reload the page once it is back.';
$string['noattemptsleft'] = 'You have no attempts left on this question.';
$string['alreadycorrect'] = 'You have already answered this question correctly.';
$string['error:notsaved'] = 'Your answer could not be marked, so it has not been recorded and it has not used up an attempt. Try again in a moment.';
$string['error:playerfailed'] = 'The video could not be loaded. Check your connection and reload the page.';
$string['error:notplayable'] = 'That address is not something the browser can play. Use a YouTube or Vimeo link, an HLS stream ending in .m3u8, or a direct link to an MP4 or WebM file.';
$string['error:novideo'] = 'Choose a video file, or switch to an address.';
$string['error:vimeofailed'] = 'The Vimeo player could not be loaded. Check that the video allows playing on this site, and that player.vimeo.com is reachable.';
$string['error:streamfailed'] = 'The stream could not be started. Check the address, and that the server hosting it allows this site to read it.';

// ---- completion -----------------------------------------------------------
$string['completionanswerall'] = 'Answer everything';
$string['completionanswerall_label'] = 'Learner must answer every question on the timeline';
$string['completionanswerall_help'] = 'Answering counts, not answering correctly. A learner who works through the whole video has done the activity; whether they got the answers right is what the grade is for.';
$string['completionanswerall_desc'] = 'Answer every question';
$string['completionwatched'] = 'Reach the end';
$string['completionwatched_label'] = 'Learner must reach the end of the video';
$string['completionwatched_help'] = 'Reaching the end is reported by the browser, so it is a record of the playhead getting there rather than proof somebody watched. Pair it with answering the questions if that matters.';
$string['completionwatched_desc'] = 'Reach the end of the video';

// ---- report ---------------------------------------------------------------
$string['report'] = 'Results';
$string['report:nobodyyet'] = 'Nobody has opened this yet.';
$string['report:byquestion'] = 'By question';
$string['report:byquestion_help'] = 'Hardest first. A question most of the class got wrong is usually a fact about the minutes of video before it, not about the class.';
$string['report:bycategory'] = 'By topic';
$string['report:bycategory_help'] = 'Weakest topic first. One question everybody misses is usually a badly worded question; a whole topic sitting at 40% is a section of the video that did not teach what it was meant to.';
$string['report:bylearner'] = 'By learner';
$string['report:learners'] = 'Learner';
$string['report:answered'] = 'Answered';
$string['report:correctshare'] = 'Got it right';
$string['report:share'] = 'Score';
$string['report:commonestwrong'] = 'Commonest wrong answer';
$string['report:struggled'] = 'Most got this wrong';
$string['report:furthest'] = 'Watched to';
$string['report:finished'] = 'Reached the end';
$string['report:uncategorised'] = '(no topic)';
$string['report:blank'] = '(left blank)';

// ---- capabilities ---------------------------------------------------------
$string['kaiiv:addinstance'] = 'Add a new interactive video';
$string['kaiiv:view'] = 'View an interactive video';
$string['kaiiv:answer'] = 'Answer questions on the timeline';
$string['kaiiv:editinteractions'] = 'Edit the timeline';
$string['kaiiv:viewreport'] = 'See how learners answered';

// ---- privacy --------------------------------------------------------------
$string['privacy:metadata:kaiiv_response'] = 'What a learner answered for each question on the timeline, and whether it was right.';
$string['privacy:metadata:kaiiv_response:userid'] = 'The learner who answered.';
$string['privacy:metadata:kaiiv_response:response'] = 'What they answered: the options they picked, or the words they typed.';
$string['privacy:metadata:kaiiv_response:attempt'] = 'Which attempt this was.';
$string['privacy:metadata:kaiiv_response:correct'] = 'Whether it was right.';
$string['privacy:metadata:kaiiv_response:timecreated'] = 'When they answered.';
$string['privacy:metadata:kaiiv_progress'] = 'How far through the video a learner has reached.';
$string['privacy:metadata:kaiiv_progress:userid'] = 'The learner.';
$string['privacy:metadata:kaiiv_progress:furthest'] = 'The furthest point reached, in seconds.';
$string['privacy:metadata:kaiiv_progress:finished'] = 'Whether they reached the end.';
$string['privacy:metadata:kaiiv_progress:timemodified'] = 'When this was last updated.';
$string['privacy:metadata:filepurpose'] = 'Videos uploaded to an interactive video are course material, not personal data. No learner information is stored in them.';
// The engine is named here because a privacy statement that lists only local
// tables is incomplete when an answer is sent somewhere to be marked — even
// when that somewhere keeps nothing.
$string['privacy:metadata:kaiiv_engine'] = 'The interactive video engine, which marks answers. It runs inside this deployment and is not reachable from the internet.';
$string['privacy:metadata:kaiiv_engine:response'] = 'What the learner answered, sent to be marked. The engine stores nothing: it answers and forgets.';

// ---- site settings --------------------------------------------------------
$string['settings:engineurl'] = 'Engine address';
$string['settings:engineurl_desc'] = 'Where the interactive video engine (kaiiv-service) runs, for example http://10.0.0.5:9200. It marks every answer, so the activity cannot run without it. Leave empty if KAISER Proctor is installed on this site: its setting is used instead.';
$string['settings:apikey'] = 'Engine key';
$string['settings:apikey_desc'] = 'The shared secret the engine was started with (KAIIV_API_KEY). Sent as the X-Proctor-Key header on every call. Leave empty if KAISER Proctor is installed on this site: its key is used instead.';

// The things that appear on top of the video.
//
// This is the half of the fork that was not forked. Upstream, every
// interaction is a separate H5P library that receives the correct answer in
// its params and decides in the browser whether the learner got it right; the
// whole point of this plugin is that it does not work that way, so none of
// those libraries could be kept.
//
// What is here instead renders a question, sends what the learner did to the
// server, and displays whatever comes back. It never compares anything. If a
// line in this file ever looks like it is deciding whether an answer is
// correct, that is the bug.
//
// One constructor covers every type rather than one per type. The forked
// Interaction class builds its content through H5P.newRunnable, which looks a
// library up by name, so a type per constructor would mean ten names to
// register and ten places for the server's list and this one to drift apart.
// Here there is one name, and the type is a field on the item — which is what
// the engine already calls it.
import $ from 'jquery';
import Log from './log';

/** Kept in step with kaiiv-service/app/types.py by tests/check_fork.py. */
const RENDERERS = {};

/**
 * Register the interaction type on the compatibility layer.
 *
 * @param {Object} H5P the shim
 * @param {Object} ctx {submit, strings}
 */
export const register = (H5P, ctx) => {
    /**
     * One interaction, whatever kind it is.
     *
     * @param {Object} params {item}
     */
    const KaiivInteraction = function(params) {
        H5P.EventDispatcher.call(this);

        const item = params.item;
        const self = this;

        /**
         * Draw it.
         *
         * @param {jQuery} $wrapper
         */
        self.attach = function($wrapper) {
            $wrapper.addClass('kaiiv-interaction')
                .attr('data-type', item.type)
                .attr('data-interaction', item.id)
                .empty();

            const render = RENDERERS[item.type];
            if (!render) {
                // A type the server sent and this file has no renderer for.
                // Visible rather than silent: an empty box on a video is a
                // support call that starts with "the question is blank", and
                // the cause is two lists that drifted apart.
                Log.error('kaiiv: no renderer for interaction type ' + item.type);
                $wrapper.append($('<div>', {
                    'class': 'alert alert-warning m-0',
                    'text': ctx.strings.unsupported,
                }));
                return;
            }

            render($wrapper, item, ctx, self);
        };

        // The fork asks these of everything it builds. Answered here rather
        // than left undefined, and answered with the truth: scoring is the
        // server's, and an interaction that claimed a score would be a second
        // number for the same thing.
        self.getScore = () => 0;
        self.getMaxScore = () => 0;
        self.getAnswerGiven = () => !!item.answered;
        self.resize = () => {};

        return self;
    };

    KaiivInteraction.machineName = 'H5P.KaiivInteraction';
    H5P.KaiivInteraction = KaiivInteraction;
};

// --------------------------------------------------------------------------
// Shared pieces
// --------------------------------------------------------------------------

/**
 * The card every interaction is drawn inside.
 *
 * @param {jQuery} $wrapper
 * @param {Object} item
 * @returns {jQuery} the body to fill
 */
const card = ($wrapper, item) => {
    const $card = $('<div>', {'class': 'card shadow kaiiv-card'});
    const $body = $('<div>', {'class': 'card-body'});

    if (item.content.text) {
        $body.append($('<p>', {
            'class': 'lead mb-3',
            'data-region': 'questiontext',
            'html': item.content.text,
        }));
    }

    $card.append($body);
    $wrapper.append($card);
    return $body;
};

/**
 * The area where the verdict appears, and the buttons under it.
 *
 * Built once and reused across attempts rather than rebuilt, so that a
 * learner who answers again is looking at the same card moving rather than a
 * new one appearing where the old one was.
 *
 * @param {jQuery} $body
 * @param {Object} ctx
 * @returns {Object} {$outcome, $verdict, $feedback, $retry}
 */
const outcomeArea = ($body, ctx) => {
    const $outcome = $('<div>', {'data-region': 'outcome', hidden: true})
        .addClass('mt-3');
    const $verdict = $('<p>', {'data-region': 'verdict', 'class': 'mb-1'});
    const $feedback = $('<p>', {'data-region': 'feedback', 'class': 'text-muted'});
    const $retry = $('<button>', {
        'type': 'button',
        'class': 'btn btn-outline-secondary',
        'data-action': 'retry',
        'text': ctx.strings.tryagain,
        hidden: true,
    });

    // The way on. Without it a learner who has just answered is left looking
    // at a card over a paused video with nothing on it to press, and has to
    // work out that the play button in the bar underneath is what resumes —
    // which it is, but a question that ends by leaving the learner stuck is
    // a question that generates support calls.
    const $continue = $('<button>', {
        'type': 'button',
        'class': 'btn btn-primary me-2',
        'data-action': 'continue',
        'text': ctx.strings.continuelabel,
        hidden: true,
    }).on('click', () => ctx.resume());

    $outcome.append($verdict, $feedback, $continue, $retry);
    $body.append($outcome);

    return {$outcome, $verdict, $feedback, $retry, $continue};
};

/**
 * Send an answer and show what came back.
 *
 * The only place any of these renderers learns whether something was right.
 *
 * @param {Object} item
 * @param {*} response
 * @param {Object} ctx
 * @param {Object} area from outcomeArea
 * @param {jQuery} $submit the button to disable while in flight
 * @param {Function} onSettled called with the verdict once it is shown
 */
const send = (item, response, ctx, area, $submit, onSettled) => {
    if ($submit) {
        $submit.prop('disabled', true);
    }

    ctx.submit(item.id, response).then((verdict) => {
        if (!verdict.ok && (verdict.error === 'no_attempts_left'
                || verdict.error === 'already_correct')) {
            // Refused by the engine rather than failed: this question is
            // done with. Saying "try again" here would be a lie the learner
            // could act on forever, so the card says why and lets them go on.
            item.answered = true;
            area.$verdict.removeClass('text-success text-danger')
                .addClass('text-warning')
                .text(verdict.error === 'already_correct'
                    ? ctx.strings.alreadycorrect : ctx.strings.noattemptsleft);
            area.$feedback.text('');
            area.$retry.prop('hidden', true);
            area.$continue.prop('hidden', false);
            area.$outcome.prop('hidden', false);
            return null;
        }
        if (!verdict.ok) {
            // Not marked. Said plainly, because the thing the learner needs to
            // know is not "an error occurred" but "you have not lost an
            // attempt" — otherwise they will not try again.
            area.$verdict.removeClass('text-success text-danger')
                .addClass('text-warning').text(ctx.strings.notsaved);
            area.$feedback.text('');
            area.$retry.prop('hidden', false);
            area.$continue.prop('hidden', true);
            area.$outcome.prop('hidden', false);
            if ($submit) {
                $submit.prop('disabled', false);
            }
            return null;
        }

        item.answered = true;
        item.correct = verdict.correct;

        area.$verdict
            .removeClass('text-warning')
            .toggleClass('text-success', verdict.correct)
            .toggleClass('text-danger', !verdict.correct)
            .text(verdict.correct ? ctx.strings.correct : ctx.strings.wrong);

        // Feedback is whatever the server chose to release. When it withheld
        // it, this is empty — and it is emptied rather than left over from a
        // previous attempt, because a stale explanation under a new verdict
        // reads as the explanation for that verdict.
        area.$feedback.html(verdict.revealed ? (verdict.feedback || '') : '');

        area.$retry.prop('hidden', verdict.correct || !verdict.mayretry);
        // Offered after every verdict, including a wrong one with a retry
        // left. The rule the video enforces is that a question has to be
        // answered, not answered correctly — the same rule the engine's due()
        // and the completion condition use — so a learner who would rather
        // move on than try again is entitled to, and the card should say so
        // rather than leave them hunting for the play button in the bar.
        area.$continue.prop('hidden', false);
        area.$outcome.prop('hidden', false);

        if (onSettled) {
            onSettled(verdict);
        }
        return verdict;
    }).catch((error) => {
        Log.error('kaiiv: submitting an answer failed', error);
        area.$verdict.addClass('text-warning').text(ctx.strings.notsaved);
        area.$outcome.prop('hidden', false);
        if ($submit) {
            $submit.prop('disabled', false);
        }
    });
};

/**
 * A text box the browser will not offer to fill in from history.
 *
 * autocomplete is set with .attr() and never in the property map, and the
 * difference is not stylistic. $('<input>', {...}) treats any key that is also
 * a jQuery method as a call to that method — and jqueryui, which player.js
 * loads for the seek bar, adds $.fn.autocomplete. So {autocomplete: 'off'}
 * stopped being an attribute and became $input.autocomplete('off'), which
 * throws. Every typed question failed to draw, stayed unanswered, and the due
 * rule then held the playhead at it for the rest of the video.
 *
 * @param {Object} attributes
 * @returns {jQuery}
 */
const typedInput = (attributes) => $('<input>', attributes).attr('autocomplete', 'off');

/**
 * @param {Object} ctx
 * @returns {jQuery}
 */
const submitButton = (ctx) => $('<button>', {
    'type': 'button',
    'class': 'btn btn-primary mt-3',
    'data-action': 'submit',
    'text': ctx.strings.submitanswer,
});

// --------------------------------------------------------------------------
// Marked types
// --------------------------------------------------------------------------

/**
 * One answer out of several.
 *
 * No submit button. An extra click that can only ever mean "yes, that one" is
 * an extra click.
 */
RENDERERS.choice = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    const $options = $('<div>', {'class': 'd-grid gap-2', 'data-region': 'options'});

    (item.content.options || []).forEach((text, index) => {
        $('<button>', {
            'type': 'button',
            'class': 'btn btn-outline-primary text-start',
            'data-option': index,
            'html': text,
        }).appendTo($options);
    });

    $body.append($options);
    const area = outcomeArea($body, ctx);

    const lock = () => $options.find('button').prop('disabled', true);
    const unlock = () => $options.find('button').prop('disabled', false);

    $options.on('click', 'button', function() {
        const chosen = parseInt($(this).attr('data-option'), 10);
        lock();
        $(this).removeClass('btn-outline-primary').addClass('btn-primary');
        send(item, [chosen], ctx, area, null, (verdict) => {
            if (!verdict.correct && verdict.mayretry) {
                return;
            }
            self.trigger('kaiiv-answered', verdict);
        });
    });

    area.$retry.on('click', () => {
        area.$outcome.prop('hidden', true);
        $options.find('button').removeClass('btn-primary')
            .addClass('btn-outline-primary');
        unlock();
    });
};

/** Several answers, ticked and then submitted. */
RENDERERS.multichoice = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    const $options = $('<div>', {'data-region': 'options'});

    (item.content.options || []).forEach((text, index) => {
        const id = 'kaiiv-opt-' + item.id + '-' + index;
        $('<div>', {'class': 'form-check'}).append(
            $('<input>', {
                'type': 'checkbox', 'class': 'form-check-input',
                'id': id, 'data-option': index,
            }),
            $('<label>', {'class': 'form-check-label', 'for': id, 'html': text})
        ).appendTo($options);
    });

    $body.append($options);
    const $submit = submitButton(ctx).appendTo($body);
    const area = outcomeArea($body, ctx);

    $submit.on('click', () => {
        const chosen = $options.find('input:checked').map(function() {
            return parseInt($(this).attr('data-option'), 10);
        }).get();

        // Refused here rather than sent. The server would refuse it too, but
        // that refusal costs a round trip and arrives as a failure instead of
        // as an instruction.
        if (!chosen.length) {
            area.$verdict.removeClass('text-success text-danger')
                .addClass('text-warning').text(ctx.strings.pickatleastone);
            area.$outcome.prop('hidden', false);
            return;
        }

        $options.find('input').prop('disabled', true);
        send(item, chosen, ctx, area, $submit, (verdict) => {
            if (!verdict.correct && verdict.mayretry) {
                return;
            }
            self.trigger('kaiiv-answered', verdict);
        });
    });

    area.$retry.on('click', () => {
        area.$outcome.prop('hidden', true);
        $options.find('input').prop('disabled', false).prop('checked', false);
        $submit.prop('disabled', false);
    });
};

/** True or false. Two buttons, answered on click like a single choice. */
RENDERERS.truefalse = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    const $options = $('<div>', {'class': 'd-grid gap-2 d-sm-flex'});

    [[true, ctx.strings.istrue], [false, ctx.strings.isfalse]].forEach(([value, label]) => {
        $('<button>', {
            'type': 'button',
            'class': 'btn btn-outline-primary flex-fill',
            'data-value': value ? '1' : '0',
            'text': label,
        }).appendTo($options);
    });

    $body.append($options);
    const area = outcomeArea($body, ctx);

    $options.on('click', 'button', function() {
        const said = $(this).attr('data-value') === '1';
        $options.find('button').prop('disabled', true);
        $(this).removeClass('btn-outline-primary').addClass('btn-primary');
        send(item, said, ctx, area, null, (verdict) => {
            if (!verdict.correct && verdict.mayretry) {
                return;
            }
            self.trigger('kaiiv-answered', verdict);
        });
    });

    area.$retry.on('click', () => {
        area.$outcome.prop('hidden', true);
        $options.find('button').prop('disabled', false)
            .removeClass('btn-primary').addClass('btn-outline-primary');
    });
};

/** Typed in. */
RENDERERS.shorttext = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    const id = 'kaiiv-typed-' + item.id;

    $body.append(
        $('<label>', {'class': 'visually-hidden', 'for': id,
            'text': ctx.strings.youranswer}),
        typedInput({
            'type': 'text', 'class': 'form-control', 'id': id,
            'data-region': 'typed', 'maxlength': 200,
        })
    );

    const $input = $body.find('#' + id);
    const $submit = submitButton(ctx).appendTo($body);
    const area = outcomeArea($body, ctx);

    const submit = () => {
        const typed = $input.val();
        if (!String(typed).trim()) {
            return;
        }
        $input.prop('disabled', true);
        send(item, typed, ctx, area, $submit, (verdict) => {
            if (!verdict.correct && verdict.mayretry) {
                return;
            }
            self.trigger('kaiiv-answered', verdict);
        });
    };

    $submit.on('click', submit);
    // Enter submits. A text field that ignores Enter is a text field people
    // press Enter in and then wonder why nothing happened.
    $input.on('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            submit();
        }
    });

    area.$retry.on('click', () => {
        area.$outcome.prop('hidden', true);
        $input.prop('disabled', false).val('').trigger('focus');
        $submit.prop('disabled', false);
    });
};

/**
 * Sentences with gaps, typed into.
 *
 * The server sends the lines with `[[n]]` where a gap goes. Splitting on that
 * marker rather than on the words means the gap positions come from the
 * server's own numbering, and a renderer that miscounted would produce a
 * visibly wrong sentence rather than a quietly misaligned answer.
 */
const gapped = (draggable) => ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    const $lines = $('<div>', {'class': 'kaiiv-gaps'});
    let $bank = null;

    (item.content.lines || []).forEach((line) => {
        const $line = $('<p>', {'class': 'mb-2'});

        String(line).split(/(\[\[\d+\]\])/).forEach((part) => {
            const match = /^\[\[(\d+)\]\]$/.exec(part);
            if (!match) {
                $line.append(document.createTextNode(part));
                return;
            }

            const gap = match[1];
            if (draggable) {
                $line.append($('<span>', {
                    'class': 'kaiiv-gap badge bg-light text-dark border',
                    'data-gap': gap,
                    'text': '     ',
                    'tabindex': 0,
                }));
            } else {
                $line.append(typedInput({
                    'type': 'text',
                    'class': 'kaiiv-gap form-control d-inline-block',
                    'style': 'width: 8rem;',
                    'data-gap': gap,
                    'maxlength': 80,
                }));
            }
        });

        $lines.append($line);
    });

    $body.append($lines);

    if (draggable) {
        $bank = $('<div>', {'class': 'kaiiv-bank d-flex flex-wrap gap-2 mt-3'});
        (item.content.bank || []).forEach((word) => {
            $('<button>', {
                'type': 'button',
                'class': 'btn btn-sm btn-outline-secondary',
                'data-word': word,
                'text': word,
            }).appendTo($bank);
        });
        $body.append($bank);

        // Click to pick a word, click a gap to place it. Dragging is offered
        // by upstream and is not offered here: a drag is unusable on a phone
        // held one-handed and unreachable from a keyboard, and this is the
        // same exercise either way.
        let picked = null;
        $bank.on('click', 'button', function() {
            $bank.find('button').removeClass('active');
            picked = $(this).addClass('active').attr('data-word');
        });
        $lines.on('click', '.kaiiv-gap', function() {
            if (picked === null) {
                // Clicking a filled gap with nothing picked empties it, which
                // is the only way back from a misplacement.
                $(this).text('     ')
                    .removeAttr('data-word');
                return;
            }
            $(this).text(picked).attr('data-word', picked);
            $bank.find('button').removeClass('active');
            picked = null;
        });
    }

    const $submit = submitButton(ctx).appendTo($body);
    const area = outcomeArea($body, ctx);

    $submit.on('click', () => {
        const filled = {};
        $lines.find('.kaiiv-gap').each(function() {
            const $gap = $(this);
            filled[$gap.attr('data-gap')] = draggable
                ? ($gap.attr('data-word') || '') : ($gap.val() || '');
        });

        $lines.find('.kaiiv-gap').prop('disabled', true);
        send(item, filled, ctx, area, $submit, (verdict) => {
            if (!verdict.correct && verdict.mayretry) {
                return;
            }
            self.trigger('kaiiv-answered', verdict);
        });
    });

    area.$retry.on('click', () => {
        area.$outcome.prop('hidden', true);
        $submit.prop('disabled', false);
        $lines.find('.kaiiv-gap').prop('disabled', false);
        if (draggable) {
            $lines.find('.kaiiv-gap').text('     ')
                .removeAttr('data-word');
            $bank.find('button').removeClass('active');
        } else {
            $lines.find('.kaiiv-gap').val('');
        }
    });
};

RENDERERS.blanks = gapped(false);
RENDERERS.dragtext = gapped(true);

/** Words picked out of a passage. */
RENDERERS.marktheword = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    const $passage = $('<p>', {'class': 'kaiiv-passage'});

    (item.content.words || []).forEach((word, index) => {
        $passage.append($('<span>', {
            'class': 'kaiiv-word',
            'role': 'checkbox',
            'aria-checked': 'false',
            'tabindex': 0,
            'data-word': index,
            'text': word,
        }), document.createTextNode(' '));
    });

    $body.append($passage);
    const $submit = submitButton(ctx).appendTo($body);
    const area = outcomeArea($body, ctx);

    const toggle = function() {
        const $word = $(this);
        const on = $word.toggleClass('marked').hasClass('marked');
        $word.attr('aria-checked', on ? 'true' : 'false');
    };

    $passage.on('click', '.kaiiv-word', toggle);
    // Reachable from a keyboard. The whole exercise is clicking words, and a
    // version of it that needs a mouse is a version some learners cannot do.
    $passage.on('keydown', '.kaiiv-word', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggle.call(this);
        }
    });

    $submit.on('click', () => {
        const marked = $passage.find('.kaiiv-word.marked').map(function() {
            return parseInt($(this).attr('data-word'), 10);
        }).get();

        $passage.find('.kaiiv-word').attr('tabindex', -1).off('click keydown');
        send(item, marked, ctx, area, $submit, (verdict) => {
            if (!verdict.correct && verdict.mayretry) {
                return;
            }
            self.trigger('kaiiv-answered', verdict);
        });
    });

    area.$retry.on('click', () => {
        area.$outcome.prop('hidden', true);
        $submit.prop('disabled', false);
        $passage.find('.kaiiv-word').removeClass('marked')
            .attr('aria-checked', 'false').attr('tabindex', 0)
            .on('click', toggle);
    });
};

// --------------------------------------------------------------------------
// Unmarked types
// --------------------------------------------------------------------------
// These still report themselves as answered, because "answer everything" as a
// completion rule is about walking through the video, and a caption is a stop
// on that walk. The grade does not count them — that division is the engine's
// and is not repeated here.

/** A caption. */
RENDERERS.label = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);
    $('<button>', {
        'type': 'button',
        'class': 'btn btn-primary mt-2',
        'data-action': 'continue',
        'text': ctx.strings.continuelabel,
    }).appendTo($body).on('click', () => {
        send(item, null, ctx, outcomeArea($body, ctx), null, () => {
            self.trigger('kaiiv-answered', {correct: true});
            ctx.resume();
        });
    });
};

/** An image. */
RENDERERS.image = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);

    $body.append($('<img>', {
        'class': 'img-fluid',
        'src': item.content.url || '',
        // Empty alt is a decision, not an omission: an image with no
        // description given by the author is decoration as far as a screen
        // reader is concerned, and inventing a description here would be
        // inventing content.
        'alt': item.content.alt || '',
    }));

    if (item.content.caption) {
        $body.append($('<p>', {'class': 'text-muted mt-2',
            'text': item.content.caption}));
    }

    $('<button>', {
        'type': 'button',
        'class': 'btn btn-primary mt-2',
        'data-action': 'continue',
        'text': ctx.strings.continuelabel,
    }).appendTo($body).on('click', () => {
        send(item, null, ctx, outcomeArea($body, ctx), null, () => {
            self.trigger('kaiiv-answered', {correct: true});
            ctx.resume();
        });
    });
};

/** A link. */
RENDERERS.link = ($wrapper, item, ctx, self) => {
    const $body = card($wrapper, item);

    $body.append($('<a>', {
        'href': item.content.url || '#',
        'text': item.content.title || item.content.url || '',
        'target': '_blank',
        // Opening in a new tab without this hands the new page a reference
        // back to ours. It is also why the video is still there when they
        // come back, which is the behaviour an author placing a link wants.
        'rel': 'noopener noreferrer',
    }));

    $('<button>', {
        'type': 'button',
        'class': 'btn btn-primary mt-3 d-block',
        'data-action': 'continue',
        'text': ctx.strings.continuelabel,
    }).appendTo($body).on('click', () => {
        send(item, null, ctx, outcomeArea($body, ctx), null, () => {
            self.trigger('kaiiv-answered', {correct: true});
            ctx.resume();
        });
    });
};

/** The type names this file can draw, for tests/check_fork.py. */
export const rendered = () => Object.keys(RENDERERS);

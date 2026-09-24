<?php
// Talking to the interactive video engine.
//
// The engine decides three things and holds none of them: what a learner may
// see of a timeline, whether an answer was right, and what the video should do
// at a given second. This plugin owns the course, the learners, the video and
// the record — everything the engine deliberately does not.
//
// The division of labour is the same one rag_client describes, pointed the
// other way. There the service owns the corpus and Moodle sends only a
// question. Here Moodle owns everything and the engine owns only the rules, so
// every call carries the rows it needs and the engine forgets them the moment
// it answers.
//
// That is what makes it shareable. The next system this is merged with brings
// its own tables and calls the same engine; if the engine held state, the two
// would be arguing about whose copy of a learner is real.
//
// Failures are returned, never thrown, and every one of them is named. An
// interactive video whose engine is unreachable has to say so on the page:
// a learner who sees a video with no questions has no way to know the activity
// is broken rather than empty, and will finish it believing they are done.

namespace mod_kaiiv;

defined('MOODLE_INTERNAL') || die();

class engine {

    /** The payload contract this plugin speaks. The engine checks it and
     *  refuses a version it has redefined fields under, so an upgrade that
     *  moves only one of the two is a clear refusal rather than a timeline
     *  built out of misread fields. */
    const CONTRACT = '1.0';

    /** Short. Every endpoint is arithmetic over data we just sent — there is
     *  no model, no disk and no second hop behind it. A call that has not come
     *  back in this long is not slow, it is gone, and a learner waiting on a
     *  question deserves the failure quickly. */
    const TIMEOUT = 10;

    /**
     * @return bool whether an engine address is configured at all
     */
    public static function is_configured(): bool {
        return self::base_url() !== '';
    }

    /**
     * @return string
     */
    protected static function base_url(): string {
        // Three places, in order.
        //
        // This plugin's own setting, so that a Moodle which has nothing else
        // of ours — a customer's existing site with the activity added to it
        // — can be pointed at the engine without installing anything more.
        //
        // Then the proctoring plugin's, where the address lives when this is
        // part of the full stack: an administrator who has to find three
        // settings pages to point one deployment at itself gets one of them
        // wrong, so ours is left empty there and theirs is read.
        //
        // Then the compose service name, correct for every deployment of our
        // own stack until somebody splits the services across hosts — and
        // that somebody will set one of the two settings above.
        foreach ([['mod_kaiiv', 'engineurl'], ['local_kaiproctor', 'kaiivserviceurl']] as [$component, $name]) {
            $url = trim((string) get_config($component, $name));
            if ($url !== '') {
                return rtrim($url, '/');
            }
        }
        return 'http://kaiiv-service:9200';
    }

    /**
     * Split authored content into what may be stored and what may not.
     *
     * Called when a teacher saves an interaction. What comes back is two
     * halves for two columns; the authored form — the one with the answers
     * written inline — is never stored, because it never leaves the engine
     * intact.
     *
     * @param string $type
     * @param array $authored
     * @return array ok/content/answers, or ok=false with a code
     */
    public static function author(string $type, array $authored): array {
        return self::post('/author', [
            'type' => $type,
            'authored' => $authored,
        ]);
    }

    /**
     * What this learner may see.
     *
     * The request carries the answers, because we stored them and the engine
     * has to know them to decide which ones have been earned. The response
     * does not, except where they have been.
     *
     * @param array $interactions rows, answers included
     * @param array $seen interaction id => what this learner has done
     * @param array $rules allowreview and maxattempts
     * @return array ok/items, or ok=false with a code
     */
    public static function timeline(array $interactions, array $seen,
            array $rules): array {
        return self::post('/timeline', [
            'interactions' => $interactions,
            'seen' => $seen,
            'rules' => $rules,
        ]);
    }

    /**
     * Mark one answer.
     *
     * @param array $interaction type, content, answers, feedback
     * @param mixed $response what the learner sent
     * @param int $attempts how many attempts they had used before this one
     * @param array $rules
     * @return array ok/correct/store/revealed/answers/feedback
     */
    public static function judge(array $interaction, $response, int $attempts,
            array $rules): array {
        return self::post('/judge', [
            'type' => $interaction['type'],
            'content' => $interaction['content'],
            'answers' => $interaction['answers'],
            'feedback' => $interaction['feedback'] ?? '',
            'response' => $response,
            'attempts' => $attempts,
            'rules' => $rules,
        ]);
    }

    /**
     * What stands between this learner and playing on from here.
     *
     * The player works this out too, and has to — it cannot ask across the
     * network on every frame. This is the copy that is the record, and it is
     * what an answer submission is checked against.
     *
     * @param array $items the output of timeline()
     * @param float $at seconds into the video
     * @return array ok/blocked/due
     */
    public static function due(array $items, float $at): array {
        return self::post('/due', ['items' => $items, 'at' => $at]);
    }

    /**
     * @param array $interactions
     * @param array $seen
     * @return array ok/correct/total/fraction
     */
    public static function score(array $interactions, array $seen): array {
        return self::post('/score', [
            'interactions' => $interactions,
            'seen' => $seen,
        ]);
    }

    /**
     * What kinds of interaction the engine supports.
     *
     * Asked rather than hard-coded, so the editing screen grows a field when
     * the engine does instead of drifting from it.
     *
     * @return array ok/types
     */
    public static function types(): array {
        return self::get('/types');
    }

    /**
     * @return array ok/version/contract, or ok=false with a code
     */
    public static function health(): array {
        return self::get('/health', false);
    }

    // ----------------------------------------------------------------------

    /**
     * @param string $path
     * @param array $payload
     * @return array
     */
    protected static function post(string $path, array $payload): array {
        global $CFG;

        // Required explicitly rather than assumed. The curl class lives in
        // filelib and is not autoloaded; a web request usually has it because
        // something else pulled it in, so the omission only shows up from CLI
        // and from scheduled tasks.
        require_once($CFG->libdir . '/filelib.php');

        $base = self::base_url();
        if ($base === '') {
            return self::fail('not_configured',
                get_string('error:notconfigured', 'mod_kaiiv'));
        }

        $payload['contract'] = self::CONTRACT;

        // ignoresecurity, for the same reason the other clients set it:
        // Moodle blocks requests to private and loopback addresses, which is
        // the right default for a URL a user supplied and the wrong one for a
        // service an administrator configured and we run beside Moodle.
        $curl = new \curl(['ignoresecurity' => true]);
        $response = $curl->post($base . $path,
            json_encode($payload, JSON_UNESCAPED_UNICODE), [
                'CURLOPT_HTTPHEADER' => self::headers(),
                'CURLOPT_TIMEOUT' => self::TIMEOUT,
                'CURLOPT_CONNECTTIMEOUT' => 5,
            ]);

        return self::read($curl, $response);
    }

    /**
     * @param string $path
     * @param bool $keyed whether the endpoint requires the shared key
     * @return array
     */
    protected static function get(string $path, bool $keyed = true): array {
        global $CFG;
        require_once($CFG->libdir . '/filelib.php');

        $base = self::base_url();
        if ($base === '') {
            return self::fail('not_configured',
                get_string('error:notconfigured', 'mod_kaiiv'));
        }

        $curl = new \curl(['ignoresecurity' => true]);
        $response = $curl->get($base . $path, [], [
            'CURLOPT_HTTPHEADER' => $keyed ? self::headers() : [],
            'CURLOPT_TIMEOUT' => self::TIMEOUT,
            'CURLOPT_CONNECTTIMEOUT' => 5,
        ]);

        return self::read($curl, $response);
    }

    /**
     * @return array
     */
    protected static function headers(): array {
        $headers = ['Content-Type: application/json'];

        // Sent as a header rather than in the body so it never lands in a log
        // line that recorded the request payload.
        //
        // Our own setting first, for a site that has only this plugin; then
        // the proctoring plugin's, which on our full stack is the one internal
        // secret the face, AI and interactive video services all share.
        $key = trim((string) get_config('mod_kaiiv', 'apikey'));
        if ($key === '') {
            $key = trim((string) get_config('local_kaiproctor', 'apikey'));
        }
        if ($key !== '') {
            $headers[] = 'X-Proctor-Key: ' . $key;
        }

        return $headers;
    }

    /**
     * Turn a curl result into something a caller can branch on.
     *
     * @param \curl $curl
     * @param string|bool $response
     * @return array
     */
    protected static function read(\curl $curl, $response): array {
        if ($curl->get_errno()) {
            return self::fail('unreachable', $curl->error);
        }

        $decoded = json_decode((string) $response, true);
        if (!is_array($decoded)) {
            // A reply that is not JSON is usually a proxy or an error page,
            // and quoting the first of it is what turns "the engine is
            // broken" into a diagnosis.
            return self::fail('malformed', substr((string) $response, 0, 200));
        }

        $info = $curl->get_info();
        $status = (int) ($info['http_code'] ?? 0);

        if ($status === 401) {
            return self::fail('bad_key',
                get_string('error:badkey', 'mod_kaiiv'));
        }
        if ($status >= 400) {
            // The engine's own named refusal, passed through rather than
            // flattened. A caller that gets "bad_authoring: no option is
            // marked correct" can show the teacher what to fix; one that gets
            // "error" cannot.
            return self::fail(
                (string) ($decoded['error'] ?? 'http_' . $status),
                (string) ($decoded['detail'] ?? ''));
        }

        return $decoded;
    }

    /**
     * @param string $code
     * @param string $detail
     * @return array
     */
    protected static function fail(string $code, string $detail): array {
        return ['ok' => false, 'error' => $code, 'detail' => $detail];
    }
}

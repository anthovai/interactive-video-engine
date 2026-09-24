<?php
// Where the video comes from.
//
// The same file as mod_kaivideo/classes/source.php, deliberately copied rather
// than shared. It is platform knowledge — how a Moodle file area becomes a URL,
// which of YouTube's six address shapes carries the id — and it decides nothing
// about a learner, so there is nothing here the engine should hold.
//
// Copied because the two activities are sold separately and a customer who buys
// one must not have to install the other. A shared library between them would
// be a third component to version, for two hundred lines that have not changed
// since they were written.
//
// Two backends, and the difference is not cosmetic. A file plays in a real
// <video> element, which the proctoring adapter already drives and which can be
// paused in the same tick a question falls due. YouTube plays in an iframe
// across a postMessage boundary, so every instruction is asynchronous and every
// reading of the playhead is a poll.
//
// Both are supported because most customers already have their videos on
// YouTube and telling them to re-host is not a real answer. But the file is the
// better one, and the difference is written down here rather than left for
// somebody to discover when a question arrives half a second late.

namespace mod_kaiiv;

defined('MOODLE_INTERNAL') || die();

class source {

    const FILE = 'file';
    const YOUTUBE = 'youtube';
    const VIMEO = 'vimeo';
    const HLS = 'hls';

    /**
     * Providers that play in a real <video> element.
     *
     * HLS is in here with plain files, and that is the whole reason it was
     * cheap to add: the stream is attached to an ordinary <video> by a library
     * Moodle already ships, so the due-question rule, the controls and the
     * proctoring adapter all carry on working with no idea anything changed.
     */
    const NATIVE = [self::FILE, self::HLS];

    /** The file area holding an uploaded video. One file, itemid 0. */
    const AREA = 'video';

    /**
     * The address the player should actually load.
     *
     * An uploaded file wins over a typed address whenever one is present. That
     * is the whole of the rule, and it is deliberately not a stored column:
     * a column saying "this one uses an upload" can disagree with whether a
     * file is there, and then the activity is broken in a way no form can show.
     * The file area is the fact; everything else reads it.
     *
     * @param \stdClass $video the kaiiv record
     * @param int $contextid the module context
     * @return string
     */
    public static function url(\stdClass $video, int $contextid): string {
        $file = self::stored_file($contextid);
        if (!$file) {
            return (string) $video->videourl;
        }

        // forcedownload false: the point is that a <video> element plays it,
        // and a Content-Disposition of attachment makes the browser offer to
        // save the lesson instead of showing it.
        return \moodle_url::make_pluginfile_url(
            $contextid, 'mod_kaiiv', self::AREA, 0, '/',
            $file->get_filename(), false)->out(false);
    }

    /**
     * The uploaded video, if there is one.
     *
     * @param int $contextid
     * @return \stored_file|null
     */
    public static function stored_file(int $contextid): ?\stored_file {
        $files = get_file_storage()->get_area_files($contextid, 'mod_kaiiv',
            self::AREA, 0, 'itemid, filepath, filename', false);
        return $files ? reset($files) : null;
    }

    /**
     * What kind of address this is, and the id if it needs one.
     *
     * @param string $url
     * @return array {provider, videoid}
     */
    public static function describe(string $url): array {
        $videoid = self::youtube_id($url);
        if ($videoid !== null) {
            return ['provider' => self::YOUTUBE, 'videoid' => $videoid];
        }

        $videoid = self::vimeo_id($url);
        if ($videoid !== null) {
            return ['provider' => self::VIMEO, 'videoid' => $videoid];
        }

        // A stream, not a file. Told apart by the extension because that is
        // what a playlist actually is: nothing about the address distinguishes
        // one otherwise, and asking the server would mean a request per page
        // load to learn something the address already says.
        return ['provider' => self::is_hls($url) ? self::HLS : self::FILE,
            'videoid' => ''];
    }

    /**
     * The numeric id out of any of Vimeo's address shapes.
     *
     * Unlisted videos carry a second hash — vimeo.com/123456789/abcdef1234 —
     * and it is not optional: without it the player refuses, so it is kept and
     * passed through as "id:hash". An unlisted video is exactly the kind a
     * customer puts a paid course behind, so dropping the hash would break the
     * case the feature exists for.
     *
     * @param string $url
     * @return string|null
     */
    public static function vimeo_id(string $url): ?string {
        $url = trim($url);
        if ($url === '') {
            return null;
        }

        $patterns = [
            // player.vimeo.com/video/ID
            '~^https?://player\.vimeo\.com/video/(\d{6,})(?:\?h=([A-Za-z0-9]+))?~',
            // vimeo.com/ID, optionally /HASH for an unlisted one
            '~^https?://(?:www\.)?vimeo\.com/(\d{6,})(?:/([A-Za-z0-9]{6,}))?~',
            // vimeo.com/channels/name/ID and /groups/name/videos/ID
            '~^https?://(?:www\.)?vimeo\.com/(?:channels/[^/]+|groups/[^/]+/videos)/(\d{6,})~',
        ];

        foreach ($patterns as $pattern) {
            if (preg_match($pattern, $url, $matches)) {
                return empty($matches[2])
                    ? $matches[1] : $matches[1] . ':' . $matches[2];
            }
        }
        return null;
    }

    /**
     * A plain embed address, for the editor's preview.
     *
     * Only the editor uses this. The player deliberately does not embed: an
     * iframe with the provider's own controls in it is an iframe a learner can
     * seek inside, where nothing in this module can intervene.
     *
     * @param array $source from describe()
     * @return string empty when the provider plays in a <video> element
     */
    public static function embed_url(array $source): string {
        if ($source['provider'] === self::YOUTUBE) {
            return 'https://www.youtube.com/embed/' . $source['videoid'];
        }

        if ($source['provider'] === self::VIMEO) {
            [$id, $hash] = array_pad(explode(':', $source['videoid'], 2), 2, '');
            return 'https://player.vimeo.com/video/' . $id
                . ($hash === '' ? '' : '?h=' . $hash);
        }

        return '';
    }

    /** Whether the address is an HLS playlist. */
    public static function is_hls(string $url): bool {
        $path = strtolower((string) parse_url(trim($url), PHP_URL_PATH));
        return substr($path, -5) === '.m3u8';
    }

    /**
     * The eleven-character id out of any of YouTube's address shapes.
     *
     * Matched rather than parsed loosely: an id is exactly eleven characters of
     * a known alphabet, and accepting anything else would put whatever the
     * author pasted into an embed URL.
     *
     * @param string $url
     * @return string|null
     */
    public static function youtube_id(string $url): ?string {
        $url = trim($url);
        if ($url === '') {
            return null;
        }

        $patterns = [
            // youtu.be/ID
            '~^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})~',
            // youtube.com/watch?v=ID
            '~^https?://(?:www\.|m\.)?youtube\.com/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})~',
            // youtube.com/embed/ID and /v/ID and /shorts/ID
            '~^https?://(?:www\.)?youtube(?:-nocookie)?\.com/(?:embed|v|shorts)/([A-Za-z0-9_-]{11})~',
        ];

        foreach ($patterns as $pattern) {
            if (preg_match($pattern, $url, $matches)) {
                return $matches[1];
            }
        }
        return null;
    }

    /** Whether an address is something one of the backends can actually play. */
    public static function is_playable(string $url): bool {
        if (self::youtube_id($url) !== null || self::vimeo_id($url) !== null
                || self::is_hls($url)) {
            return true;
        }

        // A file, then — and one the browser can decode. Checked because the
        // commonest authoring mistake is pasting a page that contains a video
        // rather than the video, and the failure otherwise appears as a blank
        // player with nothing to explain it.
        $path = strtolower((string) parse_url($url, PHP_URL_PATH));
        foreach (['.mp4', '.webm', '.ogg', '.ogv', '.m4v', '.mov'] as $extension) {
            if (substr($path, -strlen($extension)) === $extension) {
                return true;
            }
        }
        return false;
    }
}

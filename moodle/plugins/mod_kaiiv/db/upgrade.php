<?php
// Schema changes between released versions.
//
// Empty because nothing has been released yet: while version.php is still on
// 0.1.0-dev the install.xml is edited in place and databases are rebuilt. The
// file exists anyway because Moodle calls it unconditionally, and because the
// first person to add a column should find the place to write the step rather
// than have to create it.

defined('MOODLE_INTERNAL') || die();

/**
 * @param int $oldversion
 * @return bool
 */
function xmldb_kaiiv_upgrade($oldversion) {
    return true;
}

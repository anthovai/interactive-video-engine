// Where the player reports what went wrong.
//
// The console unless the page says otherwise. The Moodle adapter hands over
// core/log, so messages follow Moodle's own debugging level; a customer's page
// can hand over whatever it already reports errors through.

const sink = {
    debug: (...args) => window.console && window.console.debug(...args),
    info: (...args) => window.console && window.console.info(...args),
    warn: (...args) => window.console && window.console.warn(...args),
    error: (...args) => window.console && window.console.error(...args),
};

/**
 * @param {Object} given anything with some of debug, info, warn, error
 */
export const setLogger = (given) => {
    ['debug', 'info', 'warn', 'error'].forEach((level) => {
        if (given && typeof given[level] === 'function') {
            sink[level] = given[level].bind(given);
        }
    });
};

// A stable object whose methods are looked up at call time, so a logger set
// after the shim was imported is still the one used.
const Log = {
    debug: (...args) => sink.debug(...args),
    info: (...args) => sink.info(...args),
    warn: (...args) => sink.warn(...args),
    error: (...args) => sink.error(...args),
};

export default Log;

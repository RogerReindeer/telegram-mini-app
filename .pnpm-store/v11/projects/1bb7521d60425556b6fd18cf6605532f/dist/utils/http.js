export class HttpError extends Error {
    status;
    code;
    details;
    constructor(status, code, message, details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details;
    }
}
export function asyncRoute(fn) {
    return (req, res, next) => {
        void fn(req, res, next).catch(next);
    };
}

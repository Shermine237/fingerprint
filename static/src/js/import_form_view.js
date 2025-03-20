odoo.define('pointeur_hr.import_form_view', function (require) {
    "use strict";

    var FormController = require('web.FormController');
    var core = require('web.core');
    var _t = core._t;

    FormController.include({
        /**
         * @override
         */
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._displayMessageFromContext();
            });
        },

        /**
         * Display message stored in context
         * @private
         */
        _displayMessageFromContext: function () {
            var context = this.initialState.context || {};
            var message = context.default_message;
            
            if (message) {
                this.displayNotification({
                    title: message.title || _t('Information'),
                    message: message.message,
                    type: message.type || 'info',
                    sticky: false // Always set to false for the message to disappear
                });
            }
        }
    });
});

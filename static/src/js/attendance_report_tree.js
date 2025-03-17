odoo.define('pointeur_hr.attendance_report_tree', function (require) {
    "use strict";

    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');

    const AttendanceReportController = ListController.extend({
        buttons_template: 'PointeurHr.AttendanceReportButtons',

        _getActionMenuItems: function (state) {
            return this._super(...arguments).then((items) => {
                // Ajouter le bouton d'export dans la barre d'outils
                const exportButton = {
                    name: 'export_report',
                    string: 'Exporter',
                    icon: 'fa-download',
                    class: 'btn-primary',
                    callback: () => this._onExportReport()
                };
                items.buttons.unshift(exportButton);
                return items;
            });
        },

        _onExportReport: function () {
            // Ouvrir le wizard d'export
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'pointeur_hr.attendance.report.export.wizard',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    active_ids: this.getSelectedIds(),
                    search_domain: this.model.get(this.handle, {raw: true}).domain,
                }
            });
        }
    });

    const AttendanceReportListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: AttendanceReportController,
        }),
    });

    viewRegistry.add('attendance_report_tree', AttendanceReportListView);

    return {
        AttendanceReportController: AttendanceReportController,
        AttendanceReportListView: AttendanceReportListView,
    };
});

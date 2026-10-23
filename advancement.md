Feature fix.

in the current context. when user give ID URL and a cutoff date, you download each and every pdf and create updated pdfs. untill that step all of the flow is good.

now customers are requsting excel sheet. let me explain. under each id you should create a excel sheet called report.

inside that. you have to make a completed report. 
    - create subsheets for ex Rules, Appendixes, Waivers, Gnote
    - give a document id which identified on only for the subsheet but also for all other books donwloaded.
    - date modified or created. 
    - Book status : updated or not updated. (after compare the cutoff date.)
    - page count
    - Status (Review Pass[Green], Review Fail[Red], Issues Fixing[Yellow], In-review[Orange])

also inside summery report. make a insights like total page counts, updated page counts, numeber of books, number of updated books and any insigt may help to analyst you can list.

moving farward under each book you have to follow this step.

plan changed. we can not create subsheets. we have to go with a single sheet. lests create a column called. section. under the section mention where the PDF belongs, ex Waivers, Rules. Document id keeps same

Status should be two columns Dev Status(Todo, Inprogress, In-review, Fixing) QA status(QA PASS, QA Fail, Reviewing)

mentioned all of this under single sheet, single table.
on the right side. create a pivot table that metion summery report with improtant data.

in this fix. also focus about colors, Columns sizes, table borders too.

        
%import taco.constants

%rebase('templates/layout', title='Shutdown')
<div class="modal fade bs-modal-lg" id="shutdowncomplete" tabindex="-1" role="dialog">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-body text-center">
                <h1>{{taco.constants.APP_NAME}} is Shutdown</h1>
                <h3>You may now close the tab or browser window</h3>
            </div>
        </div>
    </div>
</div>


<div class='jumbotron text-center'>
    <h1>{{taco.constants.APP_NAME}} is shutting Down</h1>
    <div class="panel panel-default">
        <div class="panel-body text-center">
            <img id="loaderthing" src="/static/images/ajax-loader.gif" alt="loading...">
        </div>
    </div>
</div>

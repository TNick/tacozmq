/**
 * Updates the status about the peers and schedules next invocation.
 */
function update_peer_status() {
  var $api_action = {
    "action": "peerstatus",
    "data": ""
  };

  $.ajax({
    url: "/api.post",
    type: "POST",
    data: JSON.stringify($api_action),
    contentType: "application/json; charset=utf-8",
    dataType: "json",
    error: API_Alert,
    success: function (data) {
      $("#peerstatustable .loadingthing").addClass("hide");
      $uuids_that_exists = [];

      //slideout disabled peers
      $(".peerstatusrow").each(function () {
        if (!($(this).attr("id") in data)) {
          $(this).slideUp(function () {
            $(this).remove();
          });
        }
      });

      for (var $uuid in data) {
        inc = data[$uuid][0];
        out = data[$uuid][1];
        indiff = data[$uuid][2];
        outdiff = data[$uuid][3];
        nick = data[$uuid][4];
        localnick = data[$uuid][5];
        console.log(data[$uuid]);

        $inmsg = compute_message(indiff)
        $outmsg = compute_message(outdiff)

        if (localnick != "") {
          $localnickmsg = "<br>(" + localnick + ")"
        } else {
          $localnickmsg = ""
        }

        if ($("#" + $uuid).length == 1) {
          $tr = $("#" + $uuid);
          if ($tr.find(".tablenick").html() != nick) {
            $tr.find(".tablenick").html(nick);
          }
          if ($tr.find(".localnick").html() != $localnickmsg) {
            $tr.find(".localnick").html($localnickmsg);
          }
          if ($tr.find(".lastincoming").html() != $inmsg) {
            $tr.find(".lastincoming").html($inmsg);
          }
          if ($tr.find(".lastoutgoing").html() != $outmsg) {
            $tr.find(".lastoutgoing").html($outmsg);
          }
        } else {
          $tr = $("#peerstatusrowhelper");
          $tr.clone()
            .removeClass("hide")
            .addClass("peerstatusrow")
            .removeAttr("id")
            .attr("id", $uuid)
            .appendTo("#peerstatustbody");
          $tr = $("#" + $uuid);
          if ($tr.find(".tablenick").html() != nick) {
            $tr.find(".tablenick").html(nick);
          }
          if ($tr.find(".localnick").html() != $localnickmsg) {
            $tr.find(".localnick").html($localnickmsg);
          }
          if ($tr.find(".lastincoming").html() != $inmsg) {
            $tr.find(".lastincoming").html($inmsg);
          }
          if ($tr.find(".lastoutgoing").html() != $outmsg) {
            $tr.find(".lastoutgoing").html($outmsg);
          }
        }

        set_status_marker(indiff, ".incomingstatus", $tr)
        set_status_marker(outdiff, ".outgoingstatus", $tr)
      }
      setTimeout(update_peer_status, 500 + (Math.random() * 500) + 1);
    }
  });
}

function compute_message(the_diff) {
  if (the_diff < 10000000) {
    return the_diff.toFixed(2) + " second(s) ago";
  } else {
    return "Never";
  }
}

function set_status_marker(the_diff, elem, tr) {
  if (the_diff >= 6.0) {
    tr.find(elem).find(".glyphicon")
      .removeClass("glyphicon-question-sign glyphicon-ok-sign")
      .addClass("glyphicon-minus-sign");
    tr.find(elem)
      .removeClass("yellow-td green-td")
      .addClass("red-td");
  } else if (the_diff < 6.0 && the_diff >= 0.0) {
    tr.find(elem).find(".glyphicon")
      .removeClass("glyphicon-question-sign glyphicon-minus-sign")
      .addClass("glyphicon-ok-sign");
    tr.find(elem)
      .removeClass("yellow-td red-td")
      .addClass("green-td");
  }
}

function Update_Thread_Status() {
  var $api_action = {
    "action": "threadstatus",
    "data": ""
  };

  $.ajax({
    url: "/api.post",
    type: "POST",
    data: JSON.stringify($api_action),
    contentType: "application/json; charset=utf-8",
    dataType: "json",
    success: function (data) {
      if ("threads" in data) {
        if ("clients" in data["threads"]) {
          if ("alive" in data["threads"]["clients"]) {
            if (data["threads"]["clients"]["alive"]) {
              $("#clientalive").html("Running");
            } else {
              $("#clientalive").html("Stopped");
            }
          }
          if ("status" in data["threads"]["clients"]) {
            $("#clientstatus").html(data["threads"]["clients"]["status"]);
          }
          if ("lastupdate" in data["threads"]["clients"]) {
            $("#clientlast").html(data["threads"]["clients"]["lastupdate"].toFixed(2) + " second(s) ago");
          }
        }
        if ("server" in data["threads"]) {
          if ("alive" in data["threads"]["server"]) {
            if (data["threads"]["server"]["alive"]) {
              $("#serveralive").html("Running");
            } else {
              $("#serveralive").html("Stopped");
            }
          }
          if ("status" in data["threads"]["server"]) {
            $("#serverstatus").html(data["threads"]["server"]["status"]);
          }
          if ("lastupdate" in data["threads"]["server"]) {
            $("#serverlast").html(data["threads"]["server"]["lastupdate"].toFixed(2) + " second(s) ago");
          }
        }


      }
      setTimeout(Update_Thread_Status, 1500 + (Math.random() * 500) + 1);
    }
  });
}

$(document).ready(function () {
  update_peer_status();
  Update_Thread_Status();
  check_for_API_errors();
});
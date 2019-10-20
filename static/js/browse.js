var $stage = 1;
var $failcount = 0;

/**
 * 
 * @param {*} peer_uuid 
 * @param {*} sharedir 
 */
function get_share_listing_results(peer_uuid, sharedir) {
  $("#sharelisting").html("");
  $("#loaderthing").removeClass("hide");
  if ($failcount > 200) {
    $("#loaderthing").addClass("hide");
    $("#timedout").fadeIn();
  } else {
    // The payload to send to our api endpoint.
    var $api_action = {
      "action": "browseresult",
      "data": {
        "uuid": peer_uuid,
        "sharedir": sharedir
      }
    };
    $.ajax({
      url: "/api.post",
      type: "POST",
      data: JSON.stringify($api_action),
      contentType: "application/json; charset=utf-8",
      dataType: "json",
      error: API_Alert,
      success: function (data) {
        if ("result" in data) {
          $("#loaderthing").addClass("hide");
          sharelisting = [];
          if (sharedir.length > 1) {
            updir = sharedir.split('/');
            updir.pop();
            updirstr = updir.join('/');
            if (updirstr == "") {
              updirstr = "/";
            }
            the_string = '<li data-uuid="' + peer_uuid + '" data-sharedir="' + btoa(updirstr) + '" class="shareclick list-group-item">';
            the_string += '<span class="glyphicon glyphicon-arrow-left"></span> <strong>.. [BACK]</strong>';
            the_string += '</li>';
            sharelisting.push(the_string);
          }

          for (let i = 0; i < data["result"][1].length; i++) {
            if (sharedir == "/") {
              the_string = '<li data-uuid="' + peer_uuid + '" data-sharedir="' + btoa(sharedir + data["result"][1][i]) + '" class="shareclick list-group-item">';
              the_string += '<span class="glyphicon glyphicon-bookmark"></span> <strong>' + data["result"][1][i] + '</strong>';
            } else {
              the_string = '<li data-uuid="' + peer_uuid + '" data-sharedir="' + btoa(sharedir + "/" + data["result"][1][i]) + '" class="shareclick list-group-item">';
              the_string += '<span class="sharelistingbuttonblock"><div class="btn-group btn-group-xs">';
              the_string += '<button type="button" class="btn btn-default diraddtoq"><span class="glyphicon glyphicon-plus"></span></button>';
              the_string += '<button type="button" class="btn btn-default dirsubscribe"><span class="glyphicon glyphicon-tag"></span></button>';
              the_string += '</div></span>';
              the_string += '<span class="glyphicon glyphicon-folder-open"></span> <strong>' + data["result"][1][i] + '</strong>';
            }
            the_string += '</li>';
            sharelisting.push(the_string);
          }
          file_listing = [];
          for (var i = 0; i < data["result"][2].length; i++) {
            the_string = '<li data-uuid="' + peer_uuid + '" data-sharedir="' + btoa(sharedir) + '" data-filename="' + btoa(data["result"][2][i][0]) + '" data-size="' + data["result"][2][i][1] + '" data-mod="' + data["result"][2][i][2] + '" class="fileclick list-group-item">';
            the_string += '<span class="sharelistingbuttonblock"><div class="btn-group btn-group-xs">';
            the_string += '<button type="button" class="btn btn-default fileaddtoq"><span class="glyphicon glyphicon-plus"></span></button>';
            the_string += '</div></span>';
            the_string += '<span class="glyphicon glyphicon-file"></span> <strong>' + data["result"][2][i][0] + '</strong> <span style="float:right">' + commify(data["result"][2][i][1]) + ' bytes</span>';
            the_string += '</li>';
            sharelisting.push(the_string);
          }


          $output_html = '';
          $output_html += '<ul class="list-group">';
          $output_html += sharelisting.join("");
          $output_html += file_listing.join("");
          $output_html += '</ul>';
          if (sharelisting.length > 0) {
            if ($("#sharelisting").html() != $output_html) {
              $("#sharelisting").fadeOut(function () {
                $(this).html($output_html);
                $failcount = 0;
                $(".shareclick").unbind("click").click(function () {
                  l_uuid = $(this).data("uuid");
                  l_sharedir = atob($(this).data("sharedir"));
                  var $api_action = {
                    "action": "browse",
                    "data": {
                      "uuid": $(this).data("uuid"),
                      "sharedir": atob($(this).data("sharedir"))
                    }
                  };
                  $.ajax({
                    url: "/api.post",
                    type: "POST",
                    data: JSON.stringify($api_action),
                    contentType: "application/json; charset=utf-8",
                    dataType: "json",
                    error: API_Alert,
                    success: function (data) {
                      get_share_listing_results(l_uuid, l_sharedir);
                    }
                  });
                });
                $(".fileaddtoq").unbind("click").click(function (event) {
                  event.stopPropagation();
                  $(this).find("span").toggleClass("glyphicon-refresh glyphicon-plus spinner");
                  let filename = $(this).closest(".fileclick").data("filename");
                  let path = $(this).closest(".fileclick").data("sharedir");
                  let peer_uuid = $(this).closest(".fileclick").data("uuid");
                  let modtime = $(this).closest(".fileclick").data("mod");
                  let size = $(this).closest(".fileclick").data("size");
                  let buttonthis = $(this);

                  let $api_action = {
                    "action": "downloadqadd",
                    "data": {
                      "uuid": peer_uuid,
                      "sharedir": atob(path),
                      "filename": atob(filename),
                      "filesize": size,
                      "filemodtime": modtime
                    }
                  };

                  $.ajax({
                    url: "/api.post",
                    type: "POST",
                    data: JSON.stringify($api_action),
                    contentType: "application/json; charset=utf-8",
                    dataType: "json",
                    error: API_Alert,
                    success: function (data) {
                      if (data == 1) {
                        buttonthis.find("span").toggleClass("spinner glyphicon-refresh glyphicon-ok");
                        buttonthis.unbind("click");
                        buttonthis.toggleClass("btn-success");
                      } else if (data == 2) {
                        buttonthis.find("span").toggleClass("spinner glyphicon-refresh glyphicon-ok");
                        buttonthis.unbind("click");
                        buttonthis.toggleClass("btn-info");
                      } else {
                        buttonthis.find("span").toggleClass("spinner glyphicon-refresh glyphicon-remove");
                        buttonthis.unbind("click");
                        buttonthis.toggleClass("btn-danger");
                      }
                    }
                  });

                });
                $(this).fadeIn();
              });
            }
          } else {
            $("#noshares").fadeIn();
          }
        } else {
          $failcount++;
          setTimeout(function () {
            get_share_listing_results(peer_uuid, sharedir)
          }, 100);
        }
      }
    });
  }

}

/**
 * Click handler for peers in listing. Shows the shares of this particular peer.
 */
function show_peer_shares(nickname, localnick, peer_uuid) {
  $stage = 2;

  // The header.
  let $crumbs = [];
  $crumbs.push('<li><a href="/browse.taco">Return to Peer Listing</a></li>');
  if (localnick != "") {
    $crumbs.push('<li><a id="peerrootcrumb" href="#">' + nickname + ' (' + localnick + ') Share Listing</a></li>');
  } else {
    $crumbs.push('<li><a id="peerrootcrumb" href="#">' + nickname + ' Share Listing</a></li>');
  }
  $("#peercrumb").html('<ol class="breadcrumb">' + $crumbs.join("") + '</ol>');

  $("#peerlisting").addClass("hide");
  $("#sharelisting").removeClass("hide");
  $("#loaderthing").removeClass("hide");
  $("#peercrumb").slideDown(150);
  $("#peerrootcrumb").unbind("click").click(function () {
    $("#sharelisting").fadeOut(200, function () {
      // TODO: calls itself again in 200? Why?
      show_peer_shares(nickname, localnick, peer_uuid);
    });
  });

  // This is the data that we will send. As the data is not stored at api end point
  // and he peer needs to be interogated, we will receive a result handler.
  // We then need to ask the api endpoint again for the actual result.
  let $api_action = {
    "action": "browse",
    "data": {
      "uuid": peer_uuid,
      "sharedir": "/"
    }
  };
  $.ajax({
    url: "/api.post",
    type: "POST",
    data: JSON.stringify($api_action),
    contentType: "application/json; charset=utf-8",
    dataType: "json",
    error: API_Alert,
    success: function (data) {

      // We give some time to the api endpoint to retrieve the results
      // we asked for,
      setTimeout(function () {
        get_share_listing_results(peer_uuid, data["sharedir"])
      }, 100);
    }
  });
}

/**
 * Asks the API for peer names and generates a list to be shown to the user.
 */
function set_up_root_peer_names() {
  if ($stage != 1) {
    return;
  }

  // The payload for our request. We first request the
  // list of peers and store their uuid.
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

      // Create one list element per responsive peer.
      listing = [];
      for (let $uuid in data) {
        inc = data[$uuid][0];
        out = data[$uuid][1];
        indiff = data[$uuid][2];
        outdiff = data[$uuid][3];
        nick = data[$uuid][4];
        localnick = data[$uuid][5];

        // Fileter out peers that do not respond.
        if (indiff < 6.0 && indiff >= 0.0 && outdiff < 6.0 && outdiff >= 0.0) {
          the_string = `<li data-nick="${nick}" data-localnick="${localnick}"`
          the_string += `data-uuid="${$uuid}" class="peerclick list-group-item">`;
          the_string += '<span class="glyphicon glyphicon-user"></span> ';
          the_string += `<strong>${nick}</strong>`;
          if (localnick != "") {
            the_string += ` (${localnick})`;
          }
          the_string += '</li>';
          listing.push(the_string);
        }
      }

      if (listing.length > 0) {
        // We have found some peers. Add the generated html.
        $("#loaderthing").addClass("hide");
        $("#nopeers").fadeOut(function () {
          $output_html = '';
          $output_html += '<ul class="list-group">';
          $output_html += listing.join("");
          $output_html += '</ul>';

          if ($("#peerlisting").html() != $output_html) {
            $("#peerlisting").fadeOut(function () {
              $(this).html($output_html);
              $(".peerclick").unbind("click").click(function () {
                // When the user clicks on one of these peers we
                // request its shares.
                show_peer_shares(
                  $(this).data("nick"),
                  $(this).data("localnick"),
                  $(this).data("uuid"));
              });
              $(this).fadeIn(function () {
                setTimeout(set_up_root_peer_names, 1000)
              });
            });
          } else {
            setTimeout(set_up_root_peer_names, 1000);
          }
        });
      } else {
        // No peers; reschedule a scan.
        $("#loaderthing").addClass("hide");
        $("#peerlisting").fadeOut(function () {
          $("#nopeers").fadeIn(function () {
            setTimeout(set_up_root_peer_names, 1000)
          })
        });
      }

    }
  });
}

$(document).ready(function () {
  set_up_root_peer_names();
  check_for_API_errors();
});
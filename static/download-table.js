// Get data of "clicked" table, format it and serve it to the user for download
$('.download-table').on("click", function(){
  // Get the name of the table
  var classList = $(this).attr('class').split(/\s+/);
  var tblSelector;
  var filename;

  // Which table?
  if (classList[1] == "int-table-btn") {
    tblSelector = intTable;
    filename = "intTable.tsv";
  } else if (classList[1] == "prot-table-btn") {
    tblSelector = protTable;
    filename = "protTable.tsv";
  } else {
    console.log("Error: table does not exist");
  }

  // Format html
  var data = tblSelector.data();
  tblString = "";
  for (var i = 0; i < data.length; i++) {
    rowString = data[i];
    // Remove html tag from columns
    for (var j = 0; j < rowString.length; j++) {
      rowString[j] = rowString[j].replace(/<(?:.|\n)*?>/gm, '');

    }
    rowString = rowString.join("\t");
    tblString += rowString + "\n";
  }

  // Create file for download
  var a = window.document.createElement('a');
  a.href = window.URL.createObjectURL(new Blob([tblString], {type: 'text/csv'}));
  a.download = filename;
  // Append anchor to body.
  document.body.appendChild(a);
  a.click();
  // Remove anchor from body
  document.body.removeChild(a);
  console.log(tblString);
});

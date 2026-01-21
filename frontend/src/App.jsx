import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Chip,
  Container,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import SearchIcon from "@mui/icons-material/Search";
import DownloadIcon from "@mui/icons-material/Download";
import axios from "axios";

const toFormData = (files, lValue, wValue, tValue, returnCsv = false) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  formData.append("l_value", lValue);
  formData.append("w_value", wValue);
  formData.append("t_value", tValue ?? "");
  formData.append("return_csv", String(returnCsv));
  return formData;
};

const toPartsTableFormData = (files, lValue, wValue, tValue) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  formData.append("l_value", lValue ?? "");
  formData.append("w_value", wValue ?? "");
  formData.append("t_value", tValue ?? "");
  return formData;
};

const toLinesCsvFormData = (files) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  return formData;
};

function App() {
  const [files, setFiles] = useState([]);
  const [lValue, setLValue] = useState("20");
  const [wValue, setWValue] = useState("4");
  const [tValue, setTValue] = useState("2");
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const fileInputRef = useRef(null);

  const isSearchDisabled = useMemo(() => {
    return files.length === 0;
  }, [files]);

  const isLinesCsvDisabled = useMemo(() => {
    return files.length === 0;
  }, [files]);

  const handleFileChange = (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    if (selectedFiles.length === 0) {
      return;
    }

    setFiles((prev) => {
      const existingSignatures = new Set(
        prev.map((file) => `${file.name}-${file.size}-${file.lastModified}`)
      );
      const merged = [
        ...prev,
        ...selectedFiles.filter((file) => {
          const signature = `${file.name}-${file.size}-${file.lastModified}`;
          return !existingSignatures.has(signature);
        }),
      ];
      return merged;
    });

    setHasSearched(false);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const executeSearch = useCallback(
    async ({ returnCsv = false, silent = false } = {}) => {
      if (isSearchDisabled) {
        return;
      }

      if (!returnCsv && !silent) {
        setIsLoading(true);
      }
      setError("");

      try {
        if (returnCsv) {
          const response = await axios.post(
            "/api/search",
            toFormData(files, lValue, wValue, tValue, true),
            {
              responseType: "blob",
            }
          );

          const blob = new Blob([response.data], { type: "text/csv" });
          const url = window.URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.setAttribute("download", "search_results.csv");
          document.body.appendChild(link);
          link.click();
          link.remove();
          window.URL.revokeObjectURL(url);
        } else {
          const response = await axios.post(
            "/api/extract_part_numbers_from_table",
            toPartsTableFormData(files, lValue, wValue, tValue)
          );
          const flattened = response.data.flatMap((entry) =>
            entry.part_numbers.map((partNumber) => ({
              file_name: entry.file_name,
              part_number: partNumber,
            }))
          );
          setResults(flattened);
        }
      } catch (err) {
        setError(
          err.response?.data?.detail ||
            (returnCsv ? "CSVダウンロードに失敗しました。" : "検索中にエラーが発生しました。")
        );
      } finally {
        if (!returnCsv && !silent) {
          setIsLoading(false);
        }
      }
    },
    [files, lValue, wValue, tValue, isSearchDisabled]
  );

  const handleSearch = async () => {
    if (isSearchDisabled) {
      return;
    }

    await executeSearch();
    setHasSearched(true);
  };

  const handleDownloadPartsListCsv = async () => {
    if (isSearchDisabled) {
      return;
    }

    setError("");
    try {
      const response = await axios.post(
        "/api/extract_parts_list_csv",
        toPartsTableFormData(files, lValue, wValue, tValue),
        {
          responseType: "blob",
        }
      );

      const blob = new Blob([response.data], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "parts_list.csv");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.response?.data?.detail || "CSVダウンロードに失敗しました。");
    }
  };

  const handleDownloadLinesCsv = async () => {
    if (isLinesCsvDisabled) {
      return;
    }

    setError("");
    try {
      const response = await axios.post(
        "/api/extract_lines_csv",
        toLinesCsvFormData(files),
        {
          responseType: "blob",
        }
      );

      const blob = new Blob([response.data], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "pdf_lines.csv");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.response?.data?.detail || "PDF行CSVダウンロードに失敗しました。");
    }
  };

  const handleClear = () => {
    setFiles([]);
    setResults([]);
    setError("");
    setHasSearched(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveFile = (indexToRemove) => {
    setFiles((prev) => prev.filter((_, index) => index !== indexToRemove));
    setHasSearched(false);
  };

  useEffect(() => {
    if (!hasSearched) {
      return;
    }
    executeSearch({ silent: true });
  }, [executeSearch, hasSearched]);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper elevation={3} sx={{ p: 4 }}>
        <Stack spacing={3}>
          <Typography variant="h4" component="h1">
            部品番号抽出ツール
          </Typography>

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
            <Button
              variant="contained"
              component="label"
              startIcon={<CloudUploadIcon />}
            >
              PDFファイルを選択
              <input
                ref={fileInputRef}
                type="file"
                hidden
                multiple
                accept="application/pdf"
                onChange={handleFileChange}
              />
            </Button>
            <Button variant="outlined" onClick={handleClear}>
              クリア
            </Button>
            <Typography variant="body2" color="text.secondary">
              選択中: {files.length} 件
            </Typography>
          </Stack>

          {files.length > 0 && (
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {files.map((file, index) => (
                <Chip
                  key={`${file.name}-${file.lastModified}-${index}`}
                  label={file.name}
                  onDelete={() => handleRemoveFile(index)}
                />
              ))}
            </Stack>
          )}

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="L値"
              type="number"
              value={lValue}
              onChange={(event) => setLValue(event.target.value)}
              fullWidth
            />
            <TextField
              label="W値"
              type="number"
              value={wValue}
              onChange={(event) => setWValue(event.target.value)}
              fullWidth
            />
            <TextField
              label="T値 (厚み)"
              type="number"
              value={tValue}
              onChange={(event) => setTValue(event.target.value)}
              fullWidth
              helperText="空欄の場合は L/W のみで検索します"
            />
          </Stack>

          {error && <Alert severity="error">{error}</Alert>}

          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap">
            <Button
              variant="contained"
              startIcon={<SearchIcon />}
              onClick={handleSearch}
              disabled={isSearchDisabled || isLoading}
            >
              {isLoading ? "検索中..." : "検索"}
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={handleDownloadPartsListCsv}
              disabled={isSearchDisabled}
            >
              部品一覧CSVダウンロード
            </Button>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={handleDownloadLinesCsv}
              disabled={isLinesCsvDisabled}
            >
              PDF行CSVダウンロード
            </Button>
          </Stack>

          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>部品番号</TableCell>
                  <TableCell>ファイル名</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={2} align="center">
                      検索結果がここに表示されます。
                    </TableCell>
                  </TableRow>
                ) : (
                  results.map((row, index) => (
                    <TableRow key={`${row.file_name}-${index}`}>
                      <TableCell>{row.part_number}</TableCell>
                      <TableCell>{row.file_name}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Stack>
      </Paper>
    </Container>
  );
}

export default App;

AuthorCtrl = angular.module('pubAssistantClient').controller('AuthorCtrl', ['$scope', '$http', '$timeout', '$log',
    '$state', '$stateParams',
 function($scope, $http, $timeout, $log, $state, $stateParams) {
     $scope.authorQueryText = '';
     $scope.authorSearchResults = null;
     $scope.authorSearchPromise = null;
     $scope.page_size = 10;
     $scope.item_count = 0;
     $scope.keypressTimeout = 500;
     $scope.authorRequestPending = false;
     $scope.authorRequestError = false;

     $scope.authorQuery = function(query, page) {
         if (typeof(page)==='undefined') page = 1;
         var start = (page - 1) * $scope.page_size;
         if ($scope.item_count > 0) {
             end = Math.min(page * $scope.page_size - 1, $scope.item_count);
         } else {
             end = page * $scope.page_size - 1;
         }
         var headers = {'Range': 'items=' + start + '-' + end};
         $scope.authorRequestPending = true;
         $scope.authorRequestError = false;
         $scope.authorSearchResults = null;
         $http.get(urls.authorSearchUrl, {params: {'query': query}, headers: headers}).then(
             function successCallback(response) {
                 $scope.authorRequestPending = false;
                 $scope.authorSearchResults = response.data;
                 $scope.fillMostCitedArticles();
                 $scope.item_count = parseInt(response.headers('Content-Range').split('/')[1], 10);
                 $scope.updatePagination();
             }, function failCallback(response) {
                 $scope.authorRequestPending = false;
                 $scope.authorRequestError = true;
             });
     };

     $scope.gotoPage = function(page) {
         $state.go('.', {page: page});
     }

     $scope.updatePagination = function() {
         var last_page = ($scope.item_count == 0) ? 0 : Math.ceil($scope.item_count / $scope.page_size);
         var first = ($scope.page == 1) ? false : true;
         var previous = {page: $scope.page - 1, enabled: ($scope.page == 1) ? false : true};
         var next = {page: $scope.page + 1, enabled: ($scope.page == last_page && last_page !== 0) ? false : true};
         var start = Math.max($scope.page - 5, 1);
         var end = Math.min(start + 11, last_page);
         var more_left = {enabled: (start == 1) ? false : true, page_num: start - 1};
         var more_right = {enabled: (end == last_page) ? false : true, page_num: end + 1};
         var pages = [];
         for (i = start; i <=end; ++i) {
             var enabled = (i == $scope.page) ? false : true;
             pages.push({enabled: enabled, page_num: i});
         }
         $scope.pagination = {first: first, previous: previous, next: next,
             more_left:more_left, more_right:more_right, pages: pages};
     }

     $scope.onAuthorQuery = function() {
         function promise() {
            $state.go('.', {page: 1, search: $scope.authorQueryText});
         }
         if ($scope.authorSearchPromise) {
             $timeout.cancel($scope.authorSearchPromise);
         }
         length = $scope.authorQueryText.length;
         if (length > 0) {
             $scope.authorSearchPromise = $timeout(promise, $scope.keypressTimeout);
         } else {
             $scope.authorSearchResults = null;
             $scope.pagination = null;
         }
     };

     $scope.fillMostCitedArticles = function() {
        var start = 1;
        var end = 3;
        function callBackCreator(i) {
            return function(response) {
                $scope.authorSearchResults[i].mostCitedArticles = response.data;
            }
        }
        for (i = 0; i < $scope.authorSearchResults.length; ++i) {
            params = {'id': $scope.authorSearchResults[i].id};
            var headers = {'Range': 'items=' + start + '-' + end};
            $http.get(urls.authorArticlesUrl, {params: params, headers: headers}).then(
                callBackCreator(i), function failCallback(response) {
                    angular.noop();
                });
        }
     };

     if ($state.is('author-search')) {
         $scope.authorQueryText = $stateParams.search;
         if ($scope.authorQueryText.length > 0) {
            $scope.page = parseInt($stateParams.page, 10);
            $scope.authorQuery($scope.authorQueryText, $scope.page);
         }
     }
}]);